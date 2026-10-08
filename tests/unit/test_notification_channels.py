from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from backend.api.endpoints.notification_channels import router as endpoints
from backend.api.models.notification_channels import (
    ChannelCreateInput, ChannelUpdateInput, DestinationTestInput, RoutingInput,
)
from backend.db.core import Base
from backend.db.models.NotificationChannel import (
    NotificationChannel, NotificationDelivery, NotificationRoute,
)
from backend.db.models.PushNotification import PushDelivery, PushSubscription, PushVapidKey
from backend.services import notification_channels as channels
from backend.services import notification_services as services
from backend.services.notification_events import NotificationEvent, operation_event
from task_manager.scheduler.db import TaskOperation

# The endpoint functions are plain synchronous functions, so the tests call them directly.
DISCORD = {"mode": "fields", "service": "discord", "values": {"webhook_id": "123456789", "webhook_token": "abcdefghij"}}


@pytest.fixture
def channel_db(task_database, monkeypatch):
    from backend.security import crypto

    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr(crypto, "get_fernet", lambda: fernet)
    engine = task_database.kw["bind"]
    # The application enables SQLite foreign keys on every connection; cascades depend on it.
    event.listen(engine, "connect", lambda connection, _record: connection.execute("PRAGMA foreign_keys=ON"))
    engine.dispose()
    Base.metadata.create_all(
        engine,
        tables=[
            NotificationChannel.__table__, NotificationRoute.__table__, NotificationDelivery.__table__,
            PushVapidKey.__table__, PushSubscription.__table__, PushDelivery.__table__,
        ],
    )
    return task_database


def _operation(session, *, operation_id="op", status="SUCCEEDED", kind="media.download",
               resource_type="media_download", source="UI", result=None, seconds_ago=0):
    operation = TaskOperation(
        id=operation_id, kind=kind, source=source, resource_type=resource_type, resource_id=1,
        title="An episode", status=status, progress=100, completion_progress=100,
        message="Done", result=result,
        finished_at=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago),
    )
    session.add(operation)
    session.commit()
    return operation


def _backdate(session_factory, hours=2):
    """Pretend channels and routes existed before the operations in the test finished."""
    past = datetime.now(timezone.utc) - timedelta(hours=hours)
    with session_factory() as session:
        for channel in session.scalars(select(NotificationChannel)):
            channel.enabled_at = past
        for route in session.scalars(select(NotificationRoute)):
            route.created_at = past
        session.commit()


# ---------- Service catalog and URL builder ----------
def test_catalog_offers_network_services_and_hides_local_ones():
    keys = {service.key for service in services.service_catalog()}
    assert {"ntfy", "discord", "tgram", "mailto", "slack"} <= keys
    assert not keys & services.UNSUPPORTED_PROTOCOLS


@pytest.mark.parametrize("service, values, expected", [
    ("ntfy", {"schema": "ntfys", "topic": "alerts"}, "ntfys://alerts"),
    ("ntfy", {"schema": "ntfys", "topic": "alerts", "priority": "high"}, "ntfys://alerts?priority=high"),
    ("ntfy", {"schema": "ntfy", "host": "ntfy.local", "port": 8080, "targets": ["a", "b"]}, "ntfy://ntfy.local:8080/a/b"),
    ("discord", {"webhook_id": "1", "webhook_token": "t"}, "discord://1/t"),
    ("discord", {"webhook_id": "1", "webhook_token": "t", "botname": "Wire Loft"}, "discord://Wire%20Loft@1/t"),
    ("ntfy", {"schema": "ntfys", "token": "p@ss/word", "host": "h.example", "targets": ["t"]}, "ntfys://p%40ss%2Fword@h.example/t"),
])
def test_build_url_fills_the_template_that_matches_the_completed_fields(service, values, expected):
    assert services.build_url(service, values) == expected


def test_build_url_ignores_blank_fields():
    assert services.build_url("ntfy", {"schema": "ntfys", "topic": "alerts", "host": " ", "targets": []}) == "ntfys://alerts"


@pytest.mark.parametrize("service, values, message", [
    ("ntfy", {"topic": "x", "host": "h"}, "needs one of these combinations"),
    ("discord", {"webhook_id": "1"}, "needs one of these combinations"),
    ("discord", {"webhook_id": "1", "webhook_token": "t", "nonsense": "x"}, "does not use: nonsense"),
    ("ntfy", {"schema": "ftp", "topic": "x"}, "not a connection type"),
    ("not-a-service", {}, "supported notification service"),
])
def test_build_url_explains_what_is_wrong(service, values, message):
    with pytest.raises(services.InvalidDestination, match=message):
        services.build_url(service, values)


def test_masked_url_hides_credentials_and_options():
    masked = services.masked_url("discord://123456789/abcdefghij?avatar=no")
    assert "123456789" not in masked and "abcdefghij" not in masked
    assert "?" not in masked
    assert services.service_key_for_url("ntfys://alerts") == "ntfy"


@pytest.mark.parametrize("url", ["not a url", "dbus://", "vapid://x/y", "madeup://thing"])
def test_parse_destination_rejects_unusable_urls(url):
    with pytest.raises(services.InvalidDestination):
        services.parse_destination(url)


# ---------- Event classification ----------
@pytest.mark.parametrize("kwargs, expected", [
    ({}, NotificationEvent.DOWNLOAD_COMPLETED),
    ({"status": "FAILED"}, NotificationEvent.DOWNLOAD_FAILED),
    ({"status": "PARTIAL"}, NotificationEvent.DOWNLOAD_FAILED),
    ({"status": "CANCELED"}, NotificationEvent.OPERATIONS),
    ({"kind": "refresh_metadata", "resource_type": "show", "source": "SYSTEM"}, NotificationEvent.TASK_COMPLETED),
    ({"kind": "refresh_metadata", "resource_type": "show", "source": "SYSTEM", "status": "FAILED"}, NotificationEvent.TASK_FAILED),
    ({"kind": "rename", "resource_type": "show", "status": "FAILED"}, NotificationEvent.TASK_FAILED),
    ({"kind": "rename", "resource_type": "show"}, NotificationEvent.OPERATIONS),
    ({"kind": "scan", "resource_type": "show", "source": "SYSTEM",
      "result": {"summary": "found", "data": {"episodes_found": 3}}}, NotificationEvent.NEW_EPISODES),
    ({"kind": "scan", "resource_type": "show", "source": "SYSTEM",
      "result": {"summary": "none", "data": {"episodes_found": 0}}}, NotificationEvent.TASK_COMPLETED),
])
def test_operations_map_to_events(channel_db, kwargs, expected):
    with channel_db() as session:
        assert operation_event(_operation(session, **kwargs)) is expected


# ---------- Channel management ----------
def test_channel_urls_are_encrypted_and_new_channels_start_with_failures(channel_db):
    created = channels.create_channel(name="Team Discord", url="discord://123456789/abcdefghij")
    assert created.service == "discord"
    assert created.service_name == "Discord"
    assert set(created.events) == {NotificationEvent.DOWNLOAD_FAILED, NotificationEvent.TASK_FAILED}
    assert created.health is channels.ChannelHealth.UNTESTED
    with channel_db() as session:
        stored = session.scalar(select(NotificationChannel))
        assert "abcdefghij" not in stored.encrypted_url
        assert "abcdefghij" not in stored.masked_url


def test_channel_names_are_unique(channel_db):
    channels.create_channel(name="Phone", url="ntfys://alerts")
    with pytest.raises(IntegrityError):
        channels.create_channel(name="Phone", url="ntfys://other")


def test_update_replaces_destination_and_resets_health(channel_db):
    created = channels.create_channel(name="Phone", url="ntfys://alerts")
    with channel_db() as session:
        stored = session.get(NotificationChannel, created.id)
        stored.consecutive_failures, stored.last_error = 3, "nope"
        session.commit()
    updated = channels.update_channel(created.id, name="Phone 2", url="ntfys://fresh")
    assert updated.name == "Phone 2"
    assert updated.health is channels.ChannelHealth.UNTESTED
    assert updated.last_error is None


def test_unknown_channels_are_reported(channel_db):
    with pytest.raises(channels.ChannelNotFound):
        channels.update_channel(99, enabled=False)
    with pytest.raises(channels.ChannelNotFound):
        channels.delete_channel(99)
    with pytest.raises(channels.ChannelNotFound):
        channels.set_routes({99: set()})


def test_deleting_a_channel_removes_its_routes(channel_db):
    created = channels.create_channel(name="Phone", url="ntfys://alerts")
    channels.delete_channel(created.id)
    with channel_db() as session:
        assert session.scalar(select(NotificationRoute)) is None


def test_set_routes_keeps_existing_routes_and_adds_new_ones(channel_db):
    created = channels.create_channel(name="Phone", url="ntfys://alerts")
    with channel_db() as session:
        original = {r.event: r.created_at for r in session.scalars(select(NotificationRoute))}
    updated, = channels.set_routes({created.id: {NotificationEvent.DOWNLOAD_FAILED, NotificationEvent.NEW_EPISODES}})
    assert set(updated.events) == {NotificationEvent.DOWNLOAD_FAILED, NotificationEvent.NEW_EPISODES}
    with channel_db() as session:
        stored = {r.event: r.created_at for r in session.scalars(select(NotificationRoute))}
    assert stored["download_failed"] == original["download_failed"]
    assert "task_failed" not in stored
    assert stored["new_episodes"] >= original["download_failed"]


# ---------- Sending ----------
def test_send_reports_rejections_without_leaking_the_destination(monkeypatch):
    NotifyJSON = type(services.parse_destination("json://user:secret@example.com/hook"))

    monkeypatch.setattr(NotifyJSON, "send", lambda self, *args, **kwargs: False)
    delivered, error = channels._send(
        "json://user:secret@example.com/hook", title="t", body="b", notify_type=channels.NotifyType.INFO,
    )
    assert delivered is False
    assert error and "secret" not in error

    def explode(self, *args, **kwargs):
        raise RuntimeError("https://user:secret@example.com/hook is down")

    monkeypatch.setattr(NotifyJSON, "send", explode)
    delivered, error = channels._send(
        "json://user:secret@example.com/hook", title="t", body="b", notify_type=channels.NotifyType.INFO,
    )
    assert delivered is False
    assert "secret" not in error and "RuntimeError" in error


def test_error_summary_redacts_urls():
    text = "Failed to send to https://discord.com/api/webhooks/1/SECRET: 401\nsecond https://x.test/SECRET2 failed"
    summary = channels._error_summary(text, "discord://1/SECRET")
    assert "SECRET" not in summary and "[address]" in summary


def test_testing_a_saved_channel_records_its_health(channel_db, monkeypatch):
    created = channels.create_channel(name="Phone", url="ntfys://alerts")
    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: (False, "Bad token"))
    assert channels.send_test_to_channel(created.id).error == "Bad token"
    failing, = channels.list_channels()
    assert failing.health is channels.ChannelHealth.FAILING and failing.last_error == "Bad token"

    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: (True, None))
    assert channels.send_test_to_channel(created.id).delivered
    healthy, = channels.list_channels()
    assert healthy.health is channels.ChannelHealth.HEALTHY and healthy.last_error is None


# ---------- Background delivery ----------
def test_finished_operations_reach_only_channels_routed_to_their_event(channel_db, monkeypatch):
    failures = channels.create_channel(name="Failures", url="ntfys://failures")
    completions = channels.create_channel(
        name="Completions", url="ntfys://completions", events={NotificationEvent.DOWNLOAD_COMPLETED},
    )
    _backdate(channel_db)
    with channel_db() as session:
        _operation(session, operation_id="done")

    sent = []
    monkeypatch.setattr(channels, "_send", lambda url, **kwargs: sent.append((url, kwargs)) or (True, None))
    channels.deliver_pending_channel_notifications()
    channels.deliver_pending_channel_notifications()

    assert [url for url, _ in sent] == ["ntfys://completions"]
    assert sent[0][1]["title"] == "WireLoft: An episode completed"
    assert sent[0][1]["notify_type"] is channels.NotifyType.SUCCESS
    with channel_db() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery.channel_id == completions.id and delivery.status == "SENT"
        assert delivery.attempts == 1
    assert failures.id != completions.id


def test_failed_operations_use_the_failure_notification_type(channel_db, monkeypatch):
    channels.create_channel(name="Phone", url="ntfys://alerts")
    _backdate(channel_db)
    with channel_db() as session:
        _operation(session, status="FAILED")
    seen = []
    monkeypatch.setattr(channels, "_send", lambda url, **kw: seen.append(kw["notify_type"]) or (True, None))
    channels.deliver_pending_channel_notifications()
    assert seen == [channels.NotifyType.FAILURE]


def test_channels_do_not_replay_operations_from_before_they_existed(channel_db, monkeypatch):
    with channel_db() as session:
        _operation(session, operation_id="old", status="FAILED", seconds_ago=30)
    channels.create_channel(name="Phone", url="ntfys://alerts")
    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: pytest.fail("Old operation replayed"))
    channels.deliver_pending_channel_notifications()


def test_new_routes_and_reenabled_channels_do_not_replay_history(channel_db, monkeypatch):
    created = channels.create_channel(name="Phone", url="ntfys://alerts")
    _backdate(channel_db)
    with channel_db() as session:
        _operation(session, operation_id="finished-while-disabled", status="FAILED", seconds_ago=60)
    channels.update_channel(created.id, enabled=False)
    channels.update_channel(created.id, enabled=True)
    channels.set_routes({created.id: {NotificationEvent.DOWNLOAD_FAILED, NotificationEvent.DOWNLOAD_COMPLETED}})
    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: pytest.fail("History replayed"))
    channels.deliver_pending_channel_notifications()


def test_disabled_channels_receive_nothing(channel_db, monkeypatch):
    created = channels.create_channel(name="Phone", url="ntfys://alerts")
    _backdate(channel_db)
    channels.update_channel(created.id, enabled=False)
    _backdate(channel_db)
    with channel_db() as session:
        _operation(session, status="FAILED")
    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: pytest.fail("Disabled channel used"))
    channels.deliver_pending_channel_notifications()


def test_failed_deliveries_retry_with_backoff_then_give_up(channel_db, monkeypatch):
    channels.create_channel(name="Phone", url="ntfys://alerts")
    _backdate(channel_db)
    with channel_db() as session:
        _operation(session, status="FAILED")
    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: (False, "Server said no"))

    for attempt in range(1, channels.MAX_ATTEMPTS + 1):
        channels.deliver_pending_channel_notifications()
        with channel_db() as session:
            delivery = session.scalar(select(NotificationDelivery))
            assert delivery.attempts == attempt
            if attempt < channels.MAX_ATTEMPTS:
                assert delivery.status == "PENDING"
                assert delivery.next_attempt_at > datetime.now(timezone.utc)
                delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                session.commit()

    with channel_db() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery.status == "FAILED" and delivery.error == "Server said no"
    channel, = channels.list_channels()
    assert channel.health is channels.ChannelHealth.FAILING and channel.last_error == "Server said no"

    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: pytest.fail("Gave up, should not retry"))
    channels.deliver_pending_channel_notifications()


def test_a_later_success_clears_the_failing_state(channel_db, monkeypatch):
    channels.create_channel(name="Phone", url="ntfys://alerts")
    _backdate(channel_db)
    with channel_db() as session:
        _operation(session, status="FAILED")
    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: (False, "Down"))
    channels.deliver_pending_channel_notifications()
    with channel_db() as session:
        delivery = session.scalar(select(NotificationDelivery))
        delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: (True, None))
    channels.deliver_pending_channel_notifications()
    channel, = channels.list_channels()
    assert channel.health is channels.ChannelHealth.HEALTHY and channel.last_error is None


def test_delivery_history_lists_channel_results_newest_first(channel_db, monkeypatch):
    created = channels.create_channel(name="Phone", url="ntfys://alerts")
    _backdate(channel_db)
    with channel_db() as session:
        _operation(session, operation_id="first", status="FAILED")
    monkeypatch.setattr(channels, "_send", lambda *_a, **_k: (True, None))
    channels.deliver_pending_channel_notifications()

    history = channels.delivery_history()
    assert len(history) == 1
    assert history[0].destination == created.name
    assert history[0].event is NotificationEvent.DOWNLOAD_FAILED and history[0].status == "SENT"


# ---------- API layer ----------
def test_destination_errors_are_reported_under_the_destination_field(channel_db):
    body = DestinationTestInput.model_validate({"destination": {
        "mode": "fields", "service": "ntfy", "values": {"topic": "x", "host": "h"},
    }})
    with pytest.raises(HTTPException) as caught:
        endpoints.preview_destination(body)
    assert caught.value.status_code == 422
    assert caught.value.detail[0]["loc"] == ["body", "destination"]


def test_preview_returns_a_masked_url(channel_db):
    preview = endpoints.preview_destination(DestinationTestInput.model_validate({"destination": DISCORD}))
    assert preview.service == "discord" and preview.service_name == "Discord"
    assert "abcdefghij" not in preview.masked_url


def test_api_creates_updates_routes_and_deletes_channels(channel_db):
    created = endpoints.create_channel(ChannelCreateInput.model_validate({
        "name": "  Team Discord ", "destination": DISCORD,
    }))
    assert created.name == "Team Discord"
    assert sorted(created.events) == ["download_failed", "task_failed"]
    assert endpoints.list_channels()[0].id == created.id

    renamed = endpoints.update_channel(created.id, ChannelUpdateInput.model_validate({"name": "Discord", "enabled": False}))
    assert renamed.name == "Discord" and renamed.health == "disabled"

    routed, = endpoints.save_routing(RoutingInput.model_validate({
        "routes": [{"channelId": created.id, "events": ["new_episodes"]}],
    }))
    assert routed.events == ["new_episodes"]

    endpoints.delete_channel(created.id)
    assert endpoints.list_channels() == []


def test_api_rejects_unknown_events_and_empty_updates():
    with pytest.raises(ValueError):
        ChannelCreateInput.model_validate({"name": "x", "destination": DISCORD, "events": ["nonsense"]})
    with pytest.raises(ValueError):
        ChannelUpdateInput.model_validate({})


def test_api_reports_missing_channels_as_404(channel_db):
    with pytest.raises(HTTPException) as caught:
        endpoints.delete_channel(404)
    assert caught.value.status_code == 404
    with pytest.raises(HTTPException) as caught:
        endpoints.save_routing(RoutingInput.model_validate({"routes": [{"channelId": 404, "events": []}]}))
    assert caught.value.status_code == 404


def test_event_and_service_catalogs_serialize(channel_db):
    events = endpoints.list_events()
    assert [event.event for event in events][:2] == ["download_completed", "download_failed"]
    ntfy = next(service for service in endpoints.list_services() if service.key == "ntfy")
    assert ntfy.name == "ntfy"
    assert any(field.key == "topic" for field in ntfy.fields)
    assert next(field for field in ntfy.fields if field.key == "schema").default == "ntfys"
    assert ntfy.model_dump(by_alias=True)["serviceUrl"]
