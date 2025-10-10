from __future__ import annotations

from typing import Optional, Literal

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
    resource_type: Literal["show", "season", "episode", "movie"]
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
    resource_id: int
    status: str
    progress: Optional[int]
    message: Optional[str]
    attempt_count: int
    max_retries: int
    last_error: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    runtime_ms: Optional[int]
