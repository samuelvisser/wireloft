from typing import Optional, Any

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, Mapped, mapped_column, declarative_base
import os
from pathlib import Path
import importlib
from sqlalchemy.engine import Engine

class DatabaseConnection:
    db_path: Path
    db: Engine
    Session: sessionmaker
    Base: Any

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db = sa.create_engine("sqlite:///" + db_path.as_posix())
        self.Session = sessionmaker(bind=self.db)
        self.Base = declarative_base()

    def create_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path.as_posix()), exist_ok=True)
        importlib.import_module("backend.db.models.MediaProfile")
        importlib.import_module("backend.db.models.Show")
        importlib.import_module("backend.db.models.Episode")
        importlib.import_module("backend.db.models.Setting")
        self.Base.metadata.create_all(bind=self.db)
DATABASE: DatabaseConnection | None = None