"""The rules: the quiet defaults, and changing them."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import NotificationRule

from .events import Event


class RuleNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DefaultRule:
    key: str
    event: Event
    enabled: bool = True
    delivery: str = "now"


# Out of the box: problems only, pushed to your devices, and the daily summary one switch away.
DEFAULT_RULES: tuple[DefaultRule, ...] = (
    DefaultRule("download_failed", Event.DOWNLOAD_FAILED),
    DefaultRule("sign_in_needed", Event.SIGN_IN_NEEDED),
    DefaultRule("disk_almost_full", Event.DISK_ALMOST_FULL),
    DefaultRule("task_failing", Event.TASK_FAILING),
    DefaultRule("update_available", Event.UPDATE_AVAILABLE),
    DefaultRule("daily_summary", Event.EVERYTHING, enabled=False, delivery="daily"),
)


def _next_position(session: Session) -> int:
    return (session.scalar(select(func.max(NotificationRule.position))) or 0) + 1


def restore_default_rules(session: Session) -> int:
    """Bring back every default rule that was deleted, without touching your own rules."""
    present = set(session.scalars(select(NotificationRule.default_key).where(NotificationRule.default_key.is_not(None))))
    added = 0
    for position, default in enumerate(DEFAULT_RULES, start=1):
        if default.key in present:
            continue
        session.add(NotificationRule(
            position=position, default_key=default.key, enabled=default.enabled, event=default.event.value,
            show_scope="any", show_ids=[], push=True, destination_ids=[], delivery=default.delivery,
            summary_time="08:00",
        ))
        added += 1
    session.flush()
    return added


def list_rules(session: Session) -> list[NotificationRule]:
    return list(session.scalars(select(NotificationRule).order_by(NotificationRule.position, NotificationRule.id)))


@dataclass
class RuleValues:
    enabled: bool
    event: Event
    show_scope: str
    show_ids: list[int] = field(default_factory=list)
    push: bool = False
    destination_ids: list[int] = field(default_factory=list)
    delivery: str = "now"
    summary_time: str = "08:00"


def _apply(rule: NotificationRule, values: RuleValues) -> None:
    rule.enabled = values.enabled
    rule.event = values.event.value
    rule.show_scope = values.show_scope
    rule.show_ids = list(values.show_ids) if values.show_scope == "chosen" else []
    rule.push = values.push
    rule.destination_ids = list(dict.fromkeys(values.destination_ids))
    rule.delivery = values.delivery
    rule.summary_time = values.summary_time


def create_rule(session: Session, values: RuleValues) -> NotificationRule:
    rule = NotificationRule(position=_next_position(session))
    _apply(rule, values)
    session.add(rule)
    session.flush()
    return rule


def get_rule(session: Session, rule_id: int) -> NotificationRule:
    rule = session.get(NotificationRule, rule_id)
    if rule is None:
        raise RuleNotFound(rule_id)
    return rule


def update_rule(session: Session, rule: NotificationRule, values: RuleValues) -> NotificationRule:
    _apply(rule, values)
    session.flush()
    return rule


def delete_rule(session: Session, rule: NotificationRule) -> None:
    session.delete(rule)
    session.flush()
