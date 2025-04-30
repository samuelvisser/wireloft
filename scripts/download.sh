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
TMPDIR="/tmp/yt-dlp-tmp"
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

# 4) Read audio and description settings
read AUDIO_ONLY AUDIO_FORMAT SAVE_DESCRIPTIONS <<EOF
$(python3 - "$CONFIG_FILE" << 'PYCODE'
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
print(f"{cfg.get('audio_only', False)} {cfg.get('audio_format','')} {cfg.get('save_descriptions', False)}")
PYCODE
)
EOF

if [ "$AUDIO_ONLY" = "True" ] || [ "$AUDIO_ONLY" = "true" ]; then
  AUDIO_FLAGS="-x"
  [ -n "$AUDIO_FORMAT" ] && AUDIO_FLAGS="$AUDIO_FLAGS --audio-format $AUDIO_FORMAT"
else
  AUDIO_FLAGS=
fi

if [ "$SAVE_DESCRIPTIONS" = "True" ] || [ "$SAVE_DESCRIPTIONS" = "true" ]; then
  DESCRIPTION_FLAG="--write-description --write-info-json"
else
  DESCRIPTION_FLAG=
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
    --restrict-filenames \
    $DESCRIPTION_FLAG \
    --match-title "\[Member Exclusive\]" \
    -o "$SHOW_NAME/${OUTPUT_TEMPLATE}" \
    "$SHOW_URL"

  # Convert .description files to .nfo files for Audiobookshelf if enabled
  if [ "$SAVE_DESCRIPTIONS" = "True" ] || [ "$SAVE_DESCRIPTIONS" = "true" ]; then
    find "$DOWNLOAD_DIR/$SHOW_NAME" -name "*.description" -type f | while read desc_file; do
      base_name="${desc_file%.description}"
      nfo_file="${base_name}.nfo"
      json_file="${base_name}.info.json"

      # Extract episode title from JSON metadata if available, otherwise fallback to filename
      if [ -f "$json_file" ]; then
        # Use Python to extract the title from JSON
        episode_title=$(python3 -c "import json; print(json.load(open('$json_file'))['title'])")
        # Remove "[Member Exclusive]" suffix if present
        episode_title=$(echo "$episode_title" | sed -E 's/ \[Member Exclusive\]$//')
      else
        # Fallback: Extract episode title from filename
        filename=$(basename "$base_name")
        # Remove date prefix and extension to get title
        episode_title=$(echo "$filename" | sed -E 's/^[0-9]{8} - //')
      fi

      # Create NFO file with proper XML format for Audiobookshelf
      echo "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" > "$nfo_file"
      echo "<episodedetails>" >> "$nfo_file"
      echo "  <title><![CDATA[$episode_title]]></title>" >> "$nfo_file"
      echo "  <plot><![CDATA[$(cat "$desc_file")]]></plot>" >> "$nfo_file"
      echo "</episodedetails>" >> "$nfo_file"

      echo "Created NFO file for $(basename "$base_name")"
    done
  fi
done
