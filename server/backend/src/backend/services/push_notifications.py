"""Server-side Web Push delivery, opt-in devices and durable operation alerts."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from apprise.plugins.vapid import NotifyVapid
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from backend.db.core import begin_write_transaction, get_session
from backend.db.models.PushNotification import PushDelivery, PushSubscription, PushVapidKey
from backend.security.crypto import decrypt_text, encrypt_text
from task_manager.scheduler.db import TaskOperation

logger = logging.getLogger(__name__)

CATEGORIES = frozenset({"downloads", "failures", "tasks", "operations"})
DEFAULT_CATEGORIES = frozenset(CATEGORIES)
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "CANCELED"})
GRACE_SECONDS = 12
PRESENCE_SECONDS = 12
MAX_ALERT_AGE = timedelta(hours=24)
MAX_ATTEMPTS = 5

# Restrict outbound traffic to known browser push providers. Subscriptions are
# browser-provided URLs, but they are client-supplied to this API and must not
# turn a self-hosted WireLoft instance into a server-side request forgery proxy.
PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)

_foreground_last_seen = 0.0


def record_foreground_poll() -> None:
    global _foreground_last_seen
    _foreground_last_seen = time.monotonic()


def foreground_recent() -> bool:
    return time.monotonic() - _foreground_last_seen < PRESENCE_SECONDS


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def validate_endpoint(endpoint: str) -> None:
    if len(endpoint) > 2048:
        raise ValueError("Push endpoint is too long")
    try:
        url = urlsplit(endpoint)
        host = (url.hostname or "").lower()
        port = url.port
    except ValueError as exc:
        raise ValueError("Invalid push endpoint") from exc
    if (
        url.scheme != "https" or port not in (None, 443)
        or not host or url.username or url.password or url.fragment
        or not any(host == suffix or host.endswith("." + suffix) for suffix in PUSH_HOST_SUFFIXES)
    ):
        raise ValueError("Push endpoint must use a supported HTTPS push service")


def validate_client_keys(p256dh: str, auth: str) -> None:
    try:
        public_bytes = _unb64url(p256dh)
        auth_bytes = _unb64url(auth)
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_bytes)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid Web Push encryption keys") from exc
    if len(public_bytes) != 65 or len(auth_bytes) != 16:
        raise ValueError("Invalid Web Push encryption key lengths")


def _private_key_from_text(text: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(_unb64url(text), "big"), ec.SECP256R1())


def _public_bytes(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )


def _get_vapid_key(session) -> ec.EllipticCurvePrivateKey:
    stored = session.get(PushVapidKey, 1)
    if stored is None:
        private_key = ec.generate_private_key(ec.SECP256R1())
        encoded = _b64url(private_key.private_numbers().private_value.to_bytes(32, "big"))
        encrypted = encrypt_text(encoded)
        if encrypted is None:
            raise RuntimeError("Unable to protect the VAPID key")
        session.add(PushVapidKey(id=1, encrypted_private_key=encrypted.decode("ascii")))
        session.flush()
        return private_key

    decoded = decrypt_text(stored.encrypted_private_key)
    if decoded is None:
        raise RuntimeError("Cannot decrypt stored Web Push signing key")
    return _private_key_from_text(decoded)


def vapid_public_key() -> str:
    with get_session() as session:
        begin_write_transaction(session)
        key = _get_vapid_key(session)
        session.commit()
        return _b64url(_public_bytes(key))


def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def upsert_subscription(*, endpoint: str, p256dh: str, auth: str, categories: set[str]) -> dict:
    validate_endpoint(endpoint)
    validate_client_keys(p256dh, auth)
    if not categories.issubset(CATEGORIES):
        raise ValueError("Unknown notification category")
    now = datetime.now(timezone.utc)
    data = json.dumps({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}})
    encrypted = encrypt_text(data)
    if encrypted is None:
        raise RuntimeError("Cannot encrypt push subscription")

    with get_session() as session:
        begin_write_transaction(session)
        stored = session.scalar(select(PushSubscription).where(
            PushSubscription.endpoint_hash == _endpoint_hash(endpoint)
        ))
        if stored is None:
            stored = PushSubscription(
                endpoint_hash=_endpoint_hash(endpoint),
                encrypted_subscription=encrypted.decode("ascii"),
                enabled_at=now,
                categories=sorted(categories),
                enabled=True,
            )
            session.add(stored)
        else:
            if not stored.enabled or set(stored.categories) != set(categories):
                # Changing categories must not retroactively notify a device
                # about operations completed while that category was disabled.
                stored.enabled_at = now
            stored.encrypted_subscription = encrypted.decode("ascii")
            stored.categories = sorted(categories)
            stored.enabled = True
        session.commit()
    return {"enabled": True, "categories": sorted(categories)}


def subscription_settings(endpoint: str) -> dict:
    with get_session() as session:
        stored = session.scalar(select(PushSubscription).where(
            PushSubscription.endpoint_hash == _endpoint_hash(endpoint),
            PushSubscription.enabled.is_(True),
        ))
        return {
            "enabled": stored is not None,
            "categories": stored.categories if stored is not None else sorted(DEFAULT_CATEGORIES),
        }


def remove_subscription(endpoint: str) -> None:
    with get_session() as session:
        begin_write_transaction(session)
        stored = session.scalar(select(PushSubscription).where(
            PushSubscription.endpoint_hash == _endpoint_hash(endpoint)
        ))
        if stored is not None:
            session.delete(stored)
        session.commit()


def operation_category(operation: TaskOperation) -> str:
    if operation.status in ("FAILED", "PARTIAL"):
        return "failures"
    if operation.kind.startswith("media.download") or operation.resource_type == "media_download":
        return "downloads"
    if operation.source != "UI" or "cron" in operation.kind or "task" in operation.kind:
        return "tasks"
    return "operations"


def operation_url(category: str, operation: TaskOperation) -> str:
    if category == "downloads" or operation.kind.startswith("media.download") or operation.resource_type == "media_download":
        return "/downloads"
    if category == "tasks":
        return "/tasks"
    if category == "failures":
        return "/tasks"
    return "/"


def notification_payload(operation: TaskOperation) -> dict:
    category = operation_category(operation)
    labels = {
        "SUCCEEDED": "completed",
        "PARTIAL": "partially completed",
        "FAILED": "failed",
        "CANCELED": "canceled",
    }
    summary = (operation.result or {}).get("summary")
    body = summary if isinstance(summary, str) and summary.strip() else operation.message
    if not body:
        body = operation.error or operation.title
    return {
        "title": f"WireLoft: {operation.title} {labels.get(operation.status, 'finished')}",
        "body": str(body)[:350],
        "operationId": operation.id,
        "url": operation_url(category, operation),
        "category": category,
    }


def _send_push(key: ec.EllipticCurvePrivateKey, subscription: dict, payload: dict) -> str:
    """Hand Web Push delivery to Apprise, retaining WireLoft's JSON payload.

    Apprise's VAPID service currently accepts a PEM key and subscription JSON.
    Both are staged in a short-lived private directory, never persisted as
    plaintext in the installation's config or database. The subscription
    remains encrypted at rest in WireLoft's own database.
    """
    validate_endpoint(subscription["endpoint"])
    subscriber = "notifications@wireloft.local"
    with TemporaryDirectory(prefix="wireloft-apprise-") as directory:
        path = Path(directory)
        keyfile = path / "vapid.pem"
        subfile = path / "subscriptions.json"
        keyfile.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        subfile.write_text(json.dumps({subscriber: subscription}), encoding="utf-8")
        keyfile.chmod(0o600)
        subfile.chmod(0o600)

        notifier = NotifyVapid(
            subscriber=subscriber,
            targets=[subscriber],
            keyfile=str(keyfile),
            subfile=str(subfile),
            include_image=False,
            ttl=60,
            request_timeout=8,
            redirects=False,
        )
        if not notifier.subscriptions.load():
            raise RuntimeError("Apprise could not load the Web Push subscription")

        # Web Push is JSON, not the formatted text Apprise normally sends to
        # email/chat providers. Calling send() preserves the exact event schema.
        accepted = notifier.send(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )
        if accepted:
            return "SENT"
        # The plugin removes 404/410 endpoints from its subscription manager.
        # Distinguish permanent expiry from a temporary failed attempt.
        if subscriber not in notifier.subscriptions:
            return "EXPIRED"
        return "RETRY"


def _enqueue_pending(session, now: datetime) -> None:
    devices = list(session.scalars(select(PushSubscription).where(
        PushSubscription.enabled.is_(True)
    )))
    if not devices:
        return
    earliest = max(min(d.enabled_at for d in devices), now - MAX_ALERT_AGE)
    operations = list(session.scalars(select(TaskOperation).where(
        TaskOperation.status.in_(TERMINAL_STATUSES),
        TaskOperation.notification_seen_at.is_(None),
        TaskOperation.push_notified_at.is_(None),
        TaskOperation.finished_at >= earliest,
        TaskOperation.finished_at <= now - timedelta(seconds=GRACE_SECONDS),
    ).order_by(TaskOperation.finished_at.desc()).limit(100)))
    if not operations:
        return
    existing = set(session.execute(select(
        PushDelivery.operation_id, PushDelivery.subscription_id, PushDelivery.operation_finished_at
    ).where(
        PushDelivery.operation_id.in_([o.id for o in operations]),
    )).all())
    for op in operations:
        category = operation_category(op)
        for device in devices:
            if (
                device.enabled_at > op.finished_at
                or category not in device.categories
                or (op.id, device.id, op.finished_at) in existing
            ):
                continue
            session.add(PushDelivery(
                operation_id=op.id,
                subscription_id=device.id,
                operation_finished_at=op.finished_at,
                status="PENDING",
                attempts=0,
                next_attempt_at=now,
            ))


def deliver_pending_notifications() -> None:
    """One bounded background delivery pass; no API request waits for a push service."""
    if foreground_recent():
        return

    # Skip a write-intent transaction entirely on installations that have not
    # opted into Web Push. This runs every few seconds alongside download work.
    with get_session() as session:
        has_devices = session.scalar(select(PushSubscription.id).where(
            PushSubscription.enabled.is_(True)
        ).limit(1)) is not None
    if not has_devices:
        return

    now = datetime.now(timezone.utc)
    with get_session() as session:
        begin_write_transaction(session)
        _enqueue_pending(session, now)
        session.commit()

    with get_session() as session:
        due = list(session.scalars(select(PushDelivery.id).where(
            PushDelivery.status == "PENDING",
            PushDelivery.next_attempt_at <= now,
        ).order_by(PushDelivery.id).limit(30)))
    if not due:
        return

    # Re-use one VAPID identity across every device and across restarts.
    with get_session() as session:
        begin_write_transaction(session)
        key = _get_vapid_key(session)
        session.commit()

    for delivery_id in due:
        if foreground_recent():
            return

        # Reserve only a short write transaction for validation. Never keep
        # an SQLite transaction open while waiting on an external push service.
        with get_session() as session:
            begin_write_transaction(session)
            delivery = session.get(PushDelivery, delivery_id)
            if delivery is None or delivery.status != "PENDING":
                session.commit()
                continue
            device = session.get(PushSubscription, delivery.subscription_id)
            operation = session.get(TaskOperation, delivery.operation_id)
            if device is None or operation is None:
                session.delete(delivery)
                session.commit()
                continue
            if (
                not device.enabled or operation.notification_seen_at is not None
                or operation.status not in TERMINAL_STATUSES
                or operation_category(operation) not in device.categories
                or operation.finished_at is None
                or operation.finished_at != delivery.operation_finished_at
                or operation.finished_at < now - MAX_ALERT_AGE
            ):
                delivery.status = "CANCELED"
                session.commit()
                continue

            decrypted = decrypt_text(device.encrypted_subscription)
            if decrypted is None:
                logger.warning("Cannot decrypt Web Push subscription; disabling device %s", device.id)
                device.enabled = False
                session.commit()
                continue
            subscription = json.loads(decrypted)
            payload = notification_payload(operation)
            device_id = device.id
            session.commit()

        try:
            status = _send_push(key, subscription, payload)
        except Exception:
            logger.exception("Apprise Web Push delivery failed for device %s", device_id)
            status = "RETRY"

        with get_session() as session:
            begin_write_transaction(session)
            delivery = session.get(PushDelivery, delivery_id)
            if delivery is None or delivery.status != "PENDING":
                session.commit()
                continue
            device = session.get(PushSubscription, delivery.subscription_id)
            operation = session.get(TaskOperation, delivery.operation_id)
            delivery.attempts += 1
            if status == "SENT":
                delivery.status = "SENT"
                delivery.sent_at = datetime.now(timezone.utc)
                if operation is not None and operation.push_notified_at is None:
                    operation.push_notified_at = delivery.sent_at
            elif status == "EXPIRED" and device is not None:
                # The browser revoked or rotated this subscription.
                session.delete(device)
            elif status == "RETRY" and delivery.attempts < MAX_ATTEMPTS:
                delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    seconds=min(600, 15 * 2 ** (delivery.attempts - 1))
                )
            else:
                delivery.status = "FAILED"
                logger.warning(
                    "Web Push provider rejected device %s with status %s",
                    device_id, status,
                )
            session.commit()


def start_push_worker() -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()

    def run() -> None:
        while not stop.wait(5):
            try:
                deliver_pending_notifications()
            except Exception:
                logger.exception("Web Push delivery pass failed")

    thread = threading.Thread(target=run, name="wireloft-web-push", daemon=True)
    thread.start()
    return stop, thread
