#!/usr/bin/env sh
set -e

CONFIG_FILE="${CONFIG_FILE:-/config/config.yml}"
CRON_TMPL="/etc/cron.d/dailywire.cron.template"
CRON_FILE="/etc/cron.d/dailywire.cron"
DOWNLOAD_CMD="python3 -m dailywire_downloader.cli"

# Sanity check
[ -f "$CONFIG_FILE" ] || {
  echo "ERROR: Config file not found at $CONFIG_FILE" >&2
  exit 1
}

# Extract 'schedule' from YAML and render the cron file
schedule=$(python3 -c '
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
s = cfg.get("schedule")
if not s:
    sys.exit("ERROR: `schedule:` key missing in config.yml")
print(s)
' "$CONFIG_FILE")

# Replace placeholder in template
sed "s|{{schedule}}|$schedule|g" "$CRON_TMPL" > "$CRON_FILE"
printf "\n" >> "$CRON_FILE"
chmod 0644 "$CRON_FILE"

# Install our cron job(s)
crontab "$CRON_FILE"

# Run one-off download immediately
echo "$(date '+%Y-%m-%d %H:%M:%S'): Initial download on startup"
$DOWNLOAD_CMD

# Start tailing the cron log in the background
tail -f /var/log/cron.log &

# Hand off to CMD (i.e. cron -f)
exec "$@"
