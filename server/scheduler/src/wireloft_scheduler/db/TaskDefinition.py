from __future__ import annotations

from typing import Optional

from sqlalchemy import Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class TaskDefinition(Base):
    __tablename__ = "task_definitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]]
    allowed_resource_types: Mapped[Optional[list[str]]] = mapped_column(JSON)
    # default max retries if not provided by schedule or trigger_now
    default_max_retries: Mapped[Optional[int]] = mapped_column(Integer)