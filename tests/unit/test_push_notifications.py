from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from backend.services import push_notifications as push
from backend.db.core import Base
from backend.db.models.PushNotification import PushDelivery, PushSubscription, PushVapidKey
from task_manager.scheduler.db import TaskOperation


def _encoded(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.fixture
def push_db(task_database, monkeypatch):
    # Keep encryption keys isolated from a real installation's configuration.
    from backend.security import crypto

    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr(crypto, "get_fernet", lambda: fernet)
    Base.metadata.create_all(
        task_database.kw["bind"],
        tables=[PushVapidKey.__table__, PushSubscription.__table__, PushDelivery.__table__],
    )
    return task_database


def _device_keys():
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
    )
    auth = bytes(range(16))
    return private, public, auth


def _register(push_db, *, categories=None):
    private, public, auth = _device_keys()
    settings = push.upsert_subscription(
        endpoint="https://fcm.googleapis.com/fcm/send/test-device",
        p256dh=_encoded(public),
        auth=_encoded(auth),
        categories=set(push.CATEGORIES if categories is None else categories),
    )
    assert settings["enabled"]
    return private, {"endpoint": "https://fcm.googleapis.com/fcm/send/test-device",
                     "keys": {"p256dh": _encoded(public), "auth": _encoded(auth)}}


def _operation(session, *, status="SUCCEEDED", minutes_ago=1, operation_id="one", source="UI"):
    now = datetime.now(timezone.utc)
    op = TaskOperation(
        id=operation_id,
        kind="media.download",
        source=source,
        resource_type="media_download",
        resource_id=1,
        title="An episode",
        status=status,
        progress=100,
        completion_progress=100,
        message="Episode downloaded",
        finished_at=now - timedelta(minutes=minutes_ago),
    )
    session.add(op)
    session.commit()
    return op.id


@pytest.mark.parametrize("url", [
    "http://fcm.googleapis.com/send",
    "https://127.0.0.1/private",
    "https://localhost:5001/api",
    "https://fcm.googleapis.com.evil.test/steal",
    "https://fcm.googleapis.com:8443/send",
    "https://user:password@fcm.googleapis.com/send",
    "https://fcm.googleapis.com/send#fragment",
])
def test_rejects_unsafe_push_endpoints(url):
    with pytest.raises(ValueError):
        push.validate_endpoint(url)


def test_apprise_transport_uses_json_payload_and_temporary_keyfiles(monkeypatch):
    from pathlib import Path
    from apprise.plugins.vapid import NotifyVapid

    private, public, auth = _device_keys()
    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-device",
        "keys": {"p256dh": _encoded(public), "auth": _encoded(auth)},
    }
    received = []

    def mock_send(self, body, **kwargs):
        received.append((body, self.keyfile, self.subfile, self.ttl))
        assert Path(self.keyfile).exists()
        assert Path(self.subfile).exists()
        assert json.loads(Path(self.subfile).read_text())["notifications@wireloft.local"] == subscription
        return True

    monkeypatch.setattr(NotifyVapid, "send", mock_send)
    payload = {"title": "WireLoft", "operationId": "123", "url": "/downloads"}
    assert push._send_push(private, subscription, payload) == "SENT"
    assert json.loads(received[0][0]) == payload
    assert received[0][3] == 60
    assert not Path(received[0][1]).exists()
    assert not Path(received[0][2]).exists()


def test_apprise_expired_and_failed_subscriptions_are_distinguished(monkeypatch):
    from apprise.plugins.vapid import NotifyVapid
    private, public, auth = _device_keys()
    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test",
        "keys": {"p256dh": _encoded(public), "auth": _encoded(auth)},
    }

    def expired(self, body, **kwargs):
        self.subscriptions.remove("notifications@wireloft.local")
        return False

    monkeypatch.setattr(NotifyVapid, "send", expired)
    assert push._send_push(private, subscription, {}) == "EXPIRED"

    monkeypatch.setattr(NotifyVapid, "send", lambda self, body, **kwargs: False)
    assert push._send_push(private, subscription, {}) == "RETRY"


def test_vapid_key_is_persisted_encrypted_and_reused(push_db):
    first = push.vapid_public_key()
    second = push.vapid_public_key()
    assert first == second
    with push_db() as session:
        stored = session.get(PushVapidKey, 1)
        assert stored is not None
        assert first not in stored.encrypted_private_key


def test_subscriptions_are_encrypted_and_preferences_are_not_backfilled(push_db):
    _private, device = _register(push_db, categories={"failures"})
    with push_db() as session:
        stored = session.scalar(select(PushSubscription))
        assert device["endpoint"] not in stored.encrypted_subscription
        first_enabled = stored.enabled_at
    push.upsert_subscription(
        endpoint=device["endpoint"], p256dh=device["keys"]["p256dh"],
        auth=device["keys"]["auth"], categories={"failures", "downloads"},
    )
    with push_db() as session:
        stored = session.scalar(select(PushSubscription))
        assert stored.categories == ["downloads", "failures"]
        assert stored.enabled_at >= first_enabled


def test_only_unseen_background_operations_are_pushed_once(push_db, monkeypatch):
    _private, _device = _register(push_db)
    with push_db() as session:
        operation_id = _operation(session)
        # This test simulates a device enabled before the operation finished.
        device = session.scalar(select(PushSubscription))
        device.enabled_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.commit()

    sent = []
    monkeypatch.setattr(push, "foreground_recent", lambda: False)
    monkeypatch.setattr(push, "_send_push", lambda *_args: sent.append(_args[-1]) or "SENT")

    push.deliver_pending_notifications()
    push.deliver_pending_notifications()

    assert len(sent) == 1
    assert sent[0]["url"] == "/downloads"
    with push_db() as session:
        operation = session.get(TaskOperation, operation_id)
        delivery = session.scalar(select(PushDelivery))
        assert operation.push_notified_at is not None
        assert delivery.status == "SENT"
        assert delivery.attempts == 1


def test_foreground_activity_prevents_push(push_db, monkeypatch):
    _register(push_db)
    with push_db() as session:
        _operation(session)
        device = session.scalar(select(PushSubscription))
        device.enabled_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.commit()
    monkeypatch.setattr(push, "foreground_recent", lambda: True)
    monkeypatch.setattr(push, "_send_push", lambda *_args: pytest.fail("Push should be suppressed"))
    push.deliver_pending_notifications()
    with push_db() as session:
        assert session.scalar(select(PushDelivery)) is None


def test_seen_operations_and_older_subscription_events_are_not_replayed(push_db, monkeypatch):
    _register(push_db)
    with push_db() as session:
        _operation(session, operation_id="seen")
        _operation(session, operation_id="before-opt-in")
        session.get(TaskOperation, "seen").notification_seen_at = datetime.now(timezone.utc)
        session.commit()
    monkeypatch.setattr(push, "foreground_recent", lambda: False)
    monkeypatch.setattr(push, "_send_push", lambda *_args: pytest.fail("Old or seen operation"))
    push.deliver_pending_notifications()
    with push_db() as session:
        assert session.scalar(select(PushDelivery)) is None


def test_restart_produces_a_new_delivery_once(push_db, monkeypatch):
    _register(push_db)
    with push_db() as session:
        operation_id = _operation(session)
        device = session.scalar(select(PushSubscription))
        device.enabled_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.commit()

    sent = []
    monkeypatch.setattr(push, "foreground_recent", lambda: False)
    monkeypatch.setattr(push, "_send_push", lambda *_args: sent.append(1) or "SENT")
    push.deliver_pending_notifications()

    with push_db() as session:
        operation = session.get(TaskOperation, operation_id)
        operation.status = "RUNNING"
        operation.push_notified_at = None
        operation.notification_seen_at = None
        operation.finished_at = None
        session.commit()
    with push_db() as session:
        operation = session.get(TaskOperation, operation_id)
        operation.status = "SUCCEEDED"
        operation.finished_at = datetime.now(timezone.utc) - timedelta(seconds=40)
        session.commit()

    push.deliver_pending_notifications()
    assert len(sent) == 2
    with push_db() as session:
        assert len(list(session.scalars(select(PushDelivery)))) == 2
