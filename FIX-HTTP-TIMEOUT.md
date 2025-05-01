
# Solution: Adding Delay Between File Existence Checks

The issue you're facing is that when yt-dlp encounters files that already exist, it processes them too quickly, leading to too many requests to the server which then starts rejecting them. The standard rate-limiting parameters (`--retry-sleep`, `--min-sleep-interval`, and `--max-sleep-interval`) don't work for skipped files because they only apply to actual downloads or retries, not file existence checks.

## Solution: Two-Phase Download Process

I recommend implementing a two-phase download process:

1. First, use yt-dlp to get a list of all video URLs without downloading them
2. Then process each URL individually with a sleep between each one

### Step 1: Add a new configuration parameter

Add this to both `config.yml` and `config.yml.default`:

```yaml
sleep_between_files: 2  # Seconds to sleep between file checks
```

### Step 2: Modify the download.sh script

Replace the current download loop (around line 98) with this two-phase approach:

```bash
# 4) Read audio, nfo, retry, and sleep settings
read AUDIO_ONLY AUDIO_FORMAT SAVE_NFO RETRY_DOWNLOAD_ALL SLEEP_BETWEEN_FILES <<EOF
$(python3 - "$CONFIG_FILE" << 'PYCODE'
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
print(f"{str(cfg.get('audio_only', False)).lower()} {cfg.get('audio_format','')} {str(cfg.get('save_nfo_file', False)).lower()} {str(cfg.get('retry_download_all', True)).lower()} {cfg.get('sleep_between_files', 2)}")
PYCODE
)
EOF

# ... [rest of the existing code] ...

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
  
  # Phase 1: Get list of video URLs without downloading
  echo "$(date '+%Y-%m-%d %H:%M:%S'): Getting video list for '$SHOW_NAME'"
  VIDEO_URLS=$(yt-dlp --cookies "$COOKIES_FILE" "${DATE_FILTER[@]}" --match-title "\[Member Exclusive\]" --flat-playlist --print "%(url)s" "$SHOW_URL")
  
  # Phase 2: Process each URL individually with sleep between
  echo "$(date '+%Y-%m-%d %H:%M:%S'): Processing videos for '$SHOW_NAME' with ${SLEEP_BETWEEN_FILES}s delay between files"
  echo "$VIDEO_URLS" | while read -r VIDEO_URL; do
    # Skip empty lines
    [ -z "$VIDEO_URL" ] && continue
    
    echo "$(date '+%Y-%m-%d %H:%M:%S'): Processing $VIDEO_URL"
    
    yt-dlp \
      --cookies "$COOKIES_FILE" \
      --download-archive "$ARCHIVE_FILE" \
      "${DATE_FILTER[@]}" \
      "${AUDIO_FLAGS[@]}" \
      "${NFO_INFO_FLAG[@]}" \
      "${EXEC_FLAG[@]}" \
      "${RETRY_DOWNLOAD_FLAG[@]}" \
      --paths temp:"$TMP_DIR" \
      --paths home:"$DOWNLOAD_DIR" \
      --cache-dir "/app/cache" \
      --no-part \
      --windows-filenames \
      --embed-metadata \
      --parse-metadata "description:(?s)(?P<meta_comment>.+)" \
      --parse-metadata "title:(?P<meta_title>.+?)(?:\s+\[Member Exclusive\])?$" \
      --parse-metadata "title:(?:Ep\.\s+(?P<meta_movement>\d+))?.*" \
      --parse-metadata "title:(?:Ep\.\s+(?P<meta_track>\d+))?.*" \
      --parse-metadata "playlist_title:(?P<meta_album>.+)" \
      --parse-metadata "playlist_title:(?P<meta_series>.+)" \
      --parse-metadata "upload_date:(?P<meta_date>\d{8})$" \
      --replace-in-metadata "meta_date" "(.{4})(.{2})(.{2})" "\1-\2-\3" \
      --parse-metadata "upload_date:(?P<meta_year>.{4}).*" \
      --min-sleep-interval 10 \
      --max-sleep-interval 25 \
      --convert-thumbnails jpg \
      --embed-thumbnail \
      "$VIDEO_URL"
    
    # Sleep between files to avoid overwhelming the server
    echo "$(date '+%Y-%m-%d %H:%M:%S'): Sleeping for ${SLEEP_BETWEEN_FILES}s before next file"
    sleep "$SLEEP_BETWEEN_FILES"
  done
done
```

## How This Solution Works

1. **Two-Phase Approach**: First gets a list of all URLs, then processes them one by one
2. **Controlled Delay**: Adds a configurable sleep between each file check
3. **Maintains Archive**: Still uses the download archive to track which files have been downloaded
4. **Configurable**: The `sleep_between_files` parameter lets you adjust the delay based on server response

This solution addresses the core issue by ensuring there's always a delay between file checks, even when files already exist. This prevents overwhelming the server with too many rapid requests.

## Alternative Approach

If the `--flat-playlist` option isn't available or doesn't work as expected, you could also use the `--playlist-items` option to download one item at a time:

```bash
# Get the total number of items in the playlist
PLAYLIST_COUNT=$(yt-dlp --cookies "$COOKIES_FILE" "${DATE_FILTER[@]}" --match-title "\[Member Exclusive\]" --flat-playlist --count "$SHOW_URL")

# Process each item individually
for i in $(seq 1 $PLAYLIST_COUNT); do
  echo "$(date '+%Y-%m-%d %H:%M:%S'): Processing item $i of $PLAYLIST_COUNT"
  
  yt-dlp \
    --cookies "$COOKIES_FILE" \
    --download-archive "$ARCHIVE_FILE" \
    "${DATE_FILTER[@]}" \
    "${AUDIO_FLAGS[@]}" \
    "${NFO_INFO_FLAG[@]}" \
    "${EXEC_FLAG[@]}" \
    "${RETRY_DOWNLOAD_FLAG[@]}" \
    --playlist-items "$i" \
    # ... rest of options ...
    "$SHOW_URL"
  
  echo "$(date '+%Y-%m-%d %H:%M:%S'): Sleeping for ${SLEEP_BETWEEN_FILES}s before next file"
  sleep "$SLEEP_BETWEEN_FILES"
done
```

Both approaches achieve the same goal of adding a delay between file checks to prevent overwhelming the server.