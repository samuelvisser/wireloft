from __future__ import annotations

from typing import Any, Optional, Literal

from backend.api.models.base import ResponseBase, RequestBase


class TaskDefinitionRead(ResponseBase):
    id: int
    key: str
    title: str
    description: Optional[str]
    allowed_resource_types: Optional[list[str]]
    default_max_retries: Optional[int]


class TaskScheduleCreate(RequestBase):
    definition_key: str
    resource_type: Literal["show", "season", "episode", "movie", "download_profile_podcast", "download_profile_series"]
    resource_id: int
    trigger: Literal["cron", "interval", "date"]
    trigger_args: dict
    max_retries: Optional[int] = None


class TaskScheduleRead(ResponseBase):
    id: int
    definition_key: str
    resource_type: str
    resource_id: int
    trigger: str
    trigger_args: dict
    active: bool
    next_run_time: Optional[str]
    max_retries: Optional[int]


class TaskRunRead(ResponseBase):
    id: int
    definition_key: str
    resource_type: str
    resource_id: Optional[int]
    status: str
    progress: Optional[int]
    message: Optional[str]
    result: Optional[dict[str, Any]]
    attempt_count: int
    max_retries: int
    last_error: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    runtime_ms: Optional[int]


class TaskLedgerEntryRead(ResponseBase):
    """Durable execution facts for one canonical TaskRun."""

    id: int
    definition_key: str
    resource_type: str
    resource_id: Optional[int]
    status: str
    message: Optional[str]
    last_error: Optional[str]
    inputs: dict[str, Any]
    result: Optional[dict[str, Any]]
    started_at: Optional[str]
    finished_at: Optional[str]
    runtime_ms: Optional[int]


class TaskLedgerPageRead(ResponseBase):
    items: list[TaskLedgerEntryRead]
    total: int
    offset: int
    limit: int
    has_more: bool
