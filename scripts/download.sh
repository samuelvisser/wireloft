#!/usr/bin/env sh
set -e

DOWNLOAD_DIR="/downloads"
ARCHIVE_FILE="$DOWNLOAD_DIR/downloaded.txt"
COOKIES_FILE="${COOKIES_FILE:-/config/cookies.txt}"
CONFIG_FILE="${CONFIG_FILE:-/config/config.yml}"

# 1) Verify prerequisites
touch "$ARCHIVE_FILE"
[ -f "$COOKIES_FILE" ] || {
  echo "ERROR: Cookies file missing at $COOKIES_FILE" >&2
  exit 1
}

# 2) Parse and iterate `shows:` from YAML
python3 - "$CONFIG_FILE" << 'PYCODE' | while read -r SHOW_URL; do
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
for url in cfg.get("shows", []):
    print(url)
PYCODE
  echo "$(date '+%Y-%m-%d %H:%M:%S'): Downloading $SHOW_URL"
  yt-dlp \
    --cookies "$COOKIES_FILE" \
    --download-archive "$ARCHIVE_FILE" \
    -o "$DOWNLOAD_DIR/%(upload_date)s - %(title)s.%(ext)s" \
    --format best \
    "$SHOW_URL"
done