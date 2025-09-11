"""
Central configuration for the dailywire_api package.
"""
from pathlib import Path

# Root of the dailywire_api package
PACKAGE_ROOT: Path = Path(__file__).resolve().parents[1]

# Root of the main project directory
PROJECT_ROOT: Path = PACKAGE_ROOT.resolve().parents[2]

# DailyWire Middleware base URL (primary)
MIDDLEWARE_API: str = "https://middleware-prod.dailywire.com/middleware"

# DailyWire Stream API base URL (media retrieval, future use)
STREAM_API: str = "https://stream.media.dailywire.com"
