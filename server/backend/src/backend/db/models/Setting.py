from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base

class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(primary_key=True)
    slug: Mapped[str]
    name: Mapped[str]
    value: Mapped[Optional[str]]
    created_date: Mapped[str]
    modified_date: Mapped[str]