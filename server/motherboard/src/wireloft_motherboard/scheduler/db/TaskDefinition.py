from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class TaskDefinition(Base):
    __tablename__ = "task_definitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(unique=True, index=True)
    title: Mapped[str]
    description: Mapped[Optional[str]]
    allowed_resource_types: Mapped[Optional[list[str]]] = mapped_column(JSON)
    default_max_retries: Mapped[Optional[int]] = mapped_column(comment="default max retries if not provided by schedule or trigger_now")


    def __repr__(self) -> str:
        return f"<TaskDefinition id={self.id} key={self.key} title={self.title} description={self.description}>"