import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, Mapped, mapped_column, declarative_base
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DEFAULT_DB_PATH = ROOT / "data" / "wireloft.db"
DB_PATH = Path(os.environ.get("WIRELOFT_DB_PATH", str(DEFAULT_DB_PATH)))
DB_URI = "sqlite:///" + DB_PATH.as_posix()

db = sa.create_engine(DB_URI)
Session = sessionmaker(bind=db)
Base = declarative_base()