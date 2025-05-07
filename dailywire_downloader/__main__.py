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
    current_dir = os.getcwd()
    default_config = os.path.join(current_dir, "config", "config.yml")
    default_cookies = os.path.join(current_dir, "config", "cookies.txt")
    default_download_dir = os.path.join(current_dir, "downloads")

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
        help="Path to the configuration file (default: $(pwd)/config/config.yml or $DW_CONFIG_FILE env var)",
        default = os.environ.get("DW_CONFIG_FILE", default_config)
    )
    parser.add_argument(
        "--cookies", 
        dest="cookies_file",
        help="Path to the cookies file (default: $(pwd)/config/cookies.txt or $DW_COOKIES_FILE env var)",
        default = os.environ.get("DW_COOKIES_FILE", default_cookies)
    )
    parser.add_argument(
        "--download-dir",
        dest="download_dir",
        help="Path to the download dir (default: $(pwd)/downloads or $DW_DOWNLOAD_DIR env var)",
        default = os.environ.get("DW_DOWNLOAD_DIR", default_download_dir)
    )
    return parser.parse_args()

def main():
    """Entry point for the dailywire-download command."""
    args = parse_args()
    try:
        download.download_shows(config_file=args.config_file, cookies_file=args.cookies_file, download_dir=args.download_dir)
        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
