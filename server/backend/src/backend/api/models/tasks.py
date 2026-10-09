from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Literal

from pydantic import AliasPath, Field

from backend.api.models.base import ResponseBase, RequestBase
from backend.api.models.pagination import CursorPageRead


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
    definition_key: str = Field(validation_alias=AliasPath("definition", "key"))
    resource_type: str
    resource_id: int
    trigger: str
    trigger_args: dict
    active: bool
    next_run_time: Optional[datetime]
    max_retries: Optional[int]


class TaskRunWaitStateRead(ResponseBase):
    reason: str
    message: Optional[str] = None
    until: Optional[float] = None


class TaskRunRead(ResponseBase):
    id: int
    definition_key: str = Field(validation_alias=AliasPath("definition", "key"))
    resource_type: str
    resource_id: Optional[int]
    status: str
    progress: Optional[int]
    wait_state: Optional[TaskRunWaitStateRead] = None
    message: Optional[str]
    result: Optional[dict[str, Any]]
    attempt_count: int
    max_retries: int
    last_error: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    runtime_ms: Optional[int]


class TaskLedgerEntryRead(ResponseBase):
    """Durable execution facts for one canonical TaskRun."""

    id: int
    definition_key: str = Field(validation_alias=AliasPath("definition", "key"))
    definition_title: str = Field(validation_alias=AliasPath("definition", "title"))
    resource_type: str
    resource_id: Optional[int]
    status: str
    progress: Optional[int]
    wait_state: Optional[TaskRunWaitStateRead] = None
    message: Optional[str]
    last_error: Optional[str]
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasPath("meta", "inputs"),
    )
    result: Optional[dict[str, Any]]
    attempt_count: int
    max_retries: int
    next_retry_at: Optional[datetime]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    runtime_ms: Optional[int]
    created_at: datetime
    updated_at: datetime


class TaskLedgerPageRead(CursorPageRead[TaskLedgerEntryRead]):
    total: int


class TaskTriggerRead(ResponseBase):
    job_id: str
