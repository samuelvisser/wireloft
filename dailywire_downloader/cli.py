"""Command-line interface for DailyWire Downloader."""

import sys
from dailywire_downloader.downloader import download_shows

def main():
    """Entry point for the dailywire-download command."""
    try:
        download_shows()
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())