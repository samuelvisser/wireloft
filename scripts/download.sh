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
[ -f "$CONFIG_FILE" ] || {
  echo "ERROR: Config file missing at $CONFIG_FILE" >&2
  exit 1
}

# 2) Load the shared output template
OUTPUT_TEMPLATE=$(python3 - "$CONFIG_FILE" << 'PYCODE'
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
out = cfg.get('output')
if not out:
    sys.exit("ERROR: `output` key missing in config.yml")
print(out)
PYCODE
)

# 3) Iterate over shows: name|url
python3 - "$CONFIG_FILE" << 'PYCODE' | while IFS='|' read -r SHOW_NAME SHOW_URL; do
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
for show in cfg.get('shows', []):
    name = show.get('name')
    url  = show.get('url')
    if not (name and url):
        sys.exit("ERROR: each show entry needs both `name` and `url`")
    # Emit name|url
    print(f"{name}|{url}")
PYCODE
  echo "$(date '+%Y-%m-%d %H:%M:%S'): Downloading '$SHOW_NAME' from $SHOW_URL"
  yt-dlp \
    --cookies "$COOKIES_FILE" \
    --download-archive "$ARCHIVE_FILE" \
    -o "$DOWNLOAD_DIR/$SHOW_NAME/${OUTPUT_TEMPLATE}" \
    --format best \
    "$SHOW_URL"
done
