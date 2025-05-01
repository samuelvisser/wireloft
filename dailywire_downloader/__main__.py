"""Main entry point for DailyWire Downloader when run as a module."""

import os
import sys
import argparse
import logging
from dailywire_downloader import download, __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download DailyWire shows using your account credentials."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"DailyWire Downloader v{__version__}"
    )
    parser.add_argument(
        "--config", 
        dest="config_file",
        help="Path to the configuration file (default: /config/config.yml or $CONFIG_FILE env var)",
        default = os.environ.get("CONFIG_FILE", "config/config.yml")
    )
    parser.add_argument(
        "--cookies", 
        dest="cookies_file",
        help="Path to the cookies file (default: /config/cookies.txt or $COOKIES_FILE env var)",
        default = os.environ.get("COOKIES_FILE", "config/cookies.txt")
    )
    return parser.parse_args()

def main():
    """Entry point for the dailywire-download command."""
    args = parse_args()
    try:
        download.download_shows(config_file=args.config_file, cookies_file=args.cookies_file)
        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
