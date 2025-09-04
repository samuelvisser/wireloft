"""
Central configuration for the backend package.
"""
import os
from pathlib import Path

# Root of the backend package
PACKAGE_ROOT: Path = Path(__file__).resolve().parents[1]

# Root of the main project directory
PROJECT_ROOT: Path = PACKAGE_ROOT.resolve().parents[2]

# Default path to the SQLite database
DEFAULT_DB_PATH: Path = Path(PROJECT_ROOT / "data" / "wireloft.db")