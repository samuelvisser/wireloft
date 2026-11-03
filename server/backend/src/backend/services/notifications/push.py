"""Push to the installed app: the signing key, the devices people opt in, and sending one message.

Sending goes through Apprise's Web Push plugin; the device's subscription stays encrypted in
WireLoft's database and is only written to a private temporary folder while one message is sent.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import PushSubscription, PushVapidKey
from backend.security.crypto import decrypt_text, encrypt_text

from .senders import Outcome

# Only known browser push services: the endpoint comes from the browser, through WireLoft's API, and must not turn
# a self-hosted WireLoft into a proxy for requests to anywhere.
PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)


class PushRejected(ValueError):
    """The browser's subscription cannot be used."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def validate_endpoint(endpoint: str) -> None:
    if len(endpoint) > 2048:
        raise PushRejected("The push address is too long")
    try:
        url = urlsplit(endpoint)
        host = (url.hostname or "").lower()
        port = url.port
    except ValueError as exc:
        raise PushRejected("The push address is not valid") from exc
    if (
        url.scheme != "https" or port not in (None, 443) or not host or url.username or url.password or url.fragment
        or not any(host == suffix or host.endswith("." + suffix) for suffix in PUSH_HOST_SUFFIXES)
    ):
        raise PushRejected("This browser's push service is not supported")


def validate_client_keys(p256dh: str, auth: str) -> None:
    try:
        public_bytes = _unb64url(p256dh)
        auth_bytes = _unb64url(auth)
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_bytes)
    except (ValueError, TypeError) as exc:
        raise PushRejected("The browser's push keys are not valid") from exc
    if len(public_bytes) != 65 or len(auth_bytes) != 16:
        raise PushRejected("The browser's push keys are not valid")


def _public_bytes(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.X962, format=serialization.PublicFormat.UncompressedPoint,
    )


def vapid_key(session: Session) -> ec.EllipticCurvePrivateKey:
    """The installation's signing key, made the first time it is needed."""
    stored = session.get(PushVapidKey, 1)
    if stored is None:
        private_key = ec.generate_private_key(ec.SECP256R1())
        encoded = _b64url(private_key.private_numbers().private_value.to_bytes(32, "big"))
        encrypted = encrypt_text(encoded)
        if encrypted is None:
            raise RuntimeError("WireLoft cannot protect the push signing key")
        session.add(PushVapidKey(id=1, encrypted_private_key=encrypted.decode("ascii")))
        session.flush()
        return private_key
    decoded = decrypt_text(stored.encrypted_private_key)
    if decoded is None:
        raise RuntimeError("WireLoft cannot read its push signing key")
    return ec.derive_private_key(int.from_bytes(_unb64url(decoded), "big"), ec.SECP256R1())


def vapid_public_key(session: Session) -> str:
    return _b64url(_public_bytes(vapid_key(session)))


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def save_subscription(
    session: Session, *, endpoint: str, p256dh: str, auth: str, device_name: str,
) -> PushSubscription:
    """Store a device that asked for push messages, or update one that asked before."""
    validate_endpoint(endpoint)
    validate_client_keys(p256dh, auth)
    encrypted = encrypt_text(json.dumps({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}))
    if encrypted is None:
        raise RuntimeError("WireLoft cannot protect the push subscription")
    stored = session.scalar(select(PushSubscription).where(PushSubscription.endpoint_hash == endpoint_hash(endpoint)))
    if stored is None:
        stored = PushSubscription(endpoint_hash=endpoint_hash(endpoint))
        session.add(stored)
    stored.encrypted_subscription = encrypted.decode("ascii")
    stored.device_name = device_name.strip()[:80] or "This device"
    session.flush()
    return stored


def find_subscription(session: Session, endpoint: str) -> PushSubscription | None:
    return session.scalar(select(PushSubscription).where(PushSubscription.endpoint_hash == endpoint_hash(endpoint)))


_TTL_SECONDS = 60
# Who runs the sender, for the push service to contact. Apple's push service refuses a subject it cannot reach, such
# as an address at a .local domain, so this is the project's public page.
_VAPID_SUBJECT = "https://github.com/samuelvisser/wireloft"


def _vapid_class():
    from apprise.plugins.vapid import NotifyVapid

    class WireloftVapid(NotifyVapid):
        """Apprise always signs ``mailto:`` plus the sender address; WireLoft has no address, so it signs its page."""

        def _jwt_token(self, audience: str) -> str:
            header = _b64url(json.dumps({"alg": "ES256", "typ": "JWT"}, separators=(",", ":")).encode())
            claims = _b64url(json.dumps({
                "aud": audience, "exp": int(time.time()) + self.vapid_jwt_expiration_sec, "sub": _VAPID_SUBJECT,
            }, separators=(",", ":")).encode())
            signature = _b64url(self.pem.sign(f"{header}.{claims}".encode()))
            return f"{header}.{claims}.{signature}"

    return WireloftVapid


def _rejection(log: str) -> Outcome:
    """What the push service answered, from Apprise's log, so History shows its reason."""
    status = re.search(r"error=(\d+)", log)
    if status is None:
        return Outcome(False, "The push service could not be reached")
    code = int(status.group(1))
    reason = re.search(r"""["']?reason["']?\s*:\s*["']([A-Za-z0-9 _.-]{1,60})["']""", log)
    detail = f" ({reason.group(1)})" if reason else ""
    # A refused request stays refused; only a busy or failing push service is worth another try.
    return Outcome(False, f"The push service answered {code}{detail}", retry=code == 429 or code >= 500)


def send_push(key: ec.EllipticCurvePrivateKey, subscription: PushSubscription, payload: dict) -> str | Outcome:
    """Send one message to one device: SENT, EXPIRED when the browser revoked it, or why it was not accepted."""
    decrypted = decrypt_text(subscription.encrypted_subscription)
    if decrypted is None:
        return "EXPIRED"
    data = json.loads(decrypted)
    validate_endpoint(data["endpoint"])
    from apprise import LogCapture

    subscriber = "notifications@wireloft.local"
    with TemporaryDirectory(prefix="wireloft-push-") as directory:
        path = Path(directory)
        keyfile, subfile = path / "vapid.pem", path / "subscriptions.json"
        keyfile.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        subfile.write_text(json.dumps({subscriber: data}), encoding="utf-8")
        keyfile.chmod(0o600)
        subfile.chmod(0o600)
        notifier = _vapid_class()(
            subscriber=subscriber, targets=[subscriber], keyfile=str(keyfile), subfile=str(subfile),
            # The push service keeps the message this long for a device that is offline; Apprise allows a minute.
            include_image=False, ttl=_TTL_SECONDS, request_timeout=8, redirects=False,
        )
        if not notifier.subscriptions.load():
            return "EXPIRED"
        # Push carries WireLoft's own JSON, which the app's service worker shows.
        with LogCapture(level=logging.DEBUG) as log:
            sent = notifier.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        if sent:
            return "SENT"
        # The plugin drops endpoints the push service answered 404 or 410 for.
        if subscriber not in notifier.subscriptions:
            return "EXPIRED"
        return _rejection(log.getvalue())
