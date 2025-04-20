#!/usr/bin/env sh
set -e

CONFIG_FILE="${CONFIG_FILE:-/config/config.yml}"
CRON_TMPL="/etc/cron.d/dailywire.cron.template"
CRON_FILE="/etc/cron.d/dailywire.cron"

# 1) Sanity check
[ -f "$CONFIG_FILE" ] || {
  echo "ERROR: Config file not found at $CONFIG_FILE" >&2
  exit 1
}

# 2) Extract 'schedule' from YAML and render the cron file
schedule=$(python3 -c '
import yaml, sys
cfg = yaml.safe_load(open(sys.argv[1]))
s = cfg.get("schedule")
if not s:
    sys.exit("ERROR: `schedule:` key missing in config.yml")
print(s)
' "$CONFIG_FILE")

# 3) Replace placeholder in template
sed "s|{{schedule}}|$schedule|g" "$CRON_TMPL" > "$CRON_FILE"
chmod 0644 "$CRON_FILE"

# 4) Install our cron job(s)
crontab "$CRON_FILE"

# 5) Hand off to CMD (i.e. cron -f)
exec "$@"