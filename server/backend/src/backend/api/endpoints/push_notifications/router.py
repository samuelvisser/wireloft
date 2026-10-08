"""All Push APIs are protected by the standard WireLoft authentication guard."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.models.push_notifications import (
    PushDeviceSettings, PushHistoryItem, PushPublicKey,
    PushSubscriptionInput, PushSubscriptionLookup,
)
from backend.db.core import get_session
from backend.services.push_notifications import (
    remove_subscription, subscription_settings, upsert_subscription,
    vapid_public_key,
)
from task_manager.scheduler.db import TaskOperation

router = APIRouter(prefix="/push", tags=["Push notifications"])


@router.get("/vapid-key", response_model=PushPublicKey)
def push_public_key():
    return PushPublicKey(public_key=vapid_public_key())


@router.post("/subscriptions", response_model=PushDeviceSettings)
def save_push_subscription(body: PushSubscriptionInput):
    return upsert_subscription(
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        categories=body.categories,
    )


@router.post("/subscription-settings", response_model=PushDeviceSettings)
def get_push_device(body: PushSubscriptionLookup):
    return subscription_settings(body.endpoint)


@router.delete("/subscriptions", status_code=204)
def delete_push_subscription(body: PushSubscriptionLookup):
    remove_subscription(body.endpoint)


@router.get("/history", response_model=list[PushHistoryItem])
def notification_history(limit: int = 75):
    with get_session() as session:
        operations = session.scalars(select(TaskOperation).where(
            TaskOperation.status.in_(("SUCCEEDED", "PARTIAL", "FAILED", "CANCELED")),
        ).order_by(TaskOperation.finished_at.desc()).limit(max(1, min(limit, 100)))).all()
        return [PushHistoryItem.model_validate(operation) for operation in operations]
