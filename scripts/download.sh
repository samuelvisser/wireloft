#!/usr/bin/env sh
set -e

# === prevent overlapping runs ===
LOCKFILE="/tmp/download.lock"
exec 9>"$LOCKFILE"
flock -n 9 || {
  echo "$(date '+%Y-%m-%d %H:%M:%S'): Another download.sh is still running; exiting."
  exit 0
}

# Make all new dirs 777 and new files 666 by default
umask 000

DOWNLOAD_DIR="/downloads"
ARCHIVE_FILE="$DOWNLOAD_DIR/downloaded.txt"
COOKIES_FILE="${COOKIES_FILE:-/config/cookies.txt}"
CONFIG_FILE="${CONFIG_FILE:-/config/config.yml}"

# 1) Verify prerequisites
mkdir -p "$DOWNLOAD_DIR"
touch "$ARCHIVE_FILE"

[ -f "$COOKIES_FILE" ] || {
  echo "ERROR: Cookies file missing at $COOKIES_FILE" >&2
  exit 1
}
[ -f "$CONFIG_FILE" ] || {
  echo "ERROR: Config file missing at $CONFIG_FILE" >&2
  exit 1
}

# 2) Read start_date → --dateafter
START_DATE=$(python3 - "$CONFIG_FILE" << 'PYCODE'
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
print(cfg.get("start_date","").strip())
PYCODE
)
if [ -n "$START_DATE" ]; then
  CLEAN_DATE=$(echo "$START_DATE" | tr -d '-')
  DATE_FILTER="--dateafter $CLEAN_DATE"
else
  DATE_FILTER=
fi

# 3) Load the shared output template
OUTPUT_TEMPLATE=$(python3 - "$CONFIG_FILE" << 'PYCODE'
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
out = cfg.get("output")
if not out:
    sys.exit("ERROR: `output` key missing in config.yml")
print(out)
PYCODE
)

# 4) Read audio settings
read AUDIO_ONLY AUDIO_FORMAT <<EOF
$(python3 - "$CONFIG_FILE" << 'PYCODE'
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
print(f"{cfg.get('audio_only', False)} {cfg.get('audio_format','')}")
PYCODE
)
EOF

if [ "$AUDIO_ONLY" = "True" ] || [ "$AUDIO_ONLY" = "true" ]; then
  AUDIO_FLAGS="-x"
  [ -n "$AUDIO_FORMAT" ] && AUDIO_FLAGS="$AUDIO_FLAGS --audio-format $AUDIO_FORMAT"
else
  AUDIO_FLAGS=
fi

# 5) Iterate shows and download
python3 - "$CONFIG_FILE" << 'PYCODE' | while IFS='|' read -r SHOW_NAME SHOW_URL; do
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
for show in cfg.get("shows", []):
    n, u = show.get("name"), show.get("url")
    if not (n and u):
        sys.exit("ERROR: each show needs `name` and `url`")
    print(f"{n}|{u}")
PYCODE
  echo "$(date '+%Y-%m-%d %H:%M:%S'): Downloading '$SHOW_NAME' from $SHOW_URL"

  yt-dlp \
    --cookies "$COOKIES_FILE" \
    --download-archive "$ARCHIVE_FILE" \
    $DATE_FILTER \
    $AUDIO_FLAGS \
    --paths temp:"$TMPDIR" \
    --paths home:"$DOWNLOAD_DIR" \
    --cache-dir "/app/cache" \
    --no-part \
    --match-title "\[Member Exclusive\]" \
    -o "$SHOW_NAME/${OUTPUT_TEMPLATE}" \
    "$SHOW_URL"
done