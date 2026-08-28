#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${WL_CONFIG_FILE:-/config/config.yml}"
DATABASE_PATH="${WL_DATABASE_PATH:-/config/wireloft.db}"
# Matches downloadSettings.downloadRoot in config/config.yml.default; not an
# env var since download_root is set via that file (see its header comment).
DOWNLOAD_ROOT=/downloads
KEYRING_DATA_HOME="${XDG_DATA_HOME:-/config/keyring/data}"
KEYRING_CONFIG_HOME="${XDG_CONFIG_HOME:-/config/keyring/config}"

# Make sure every directory backed by a volume mount actually exists. The
# database file itself is created lazily below by the backend (create_tables()
# is idempotent), never here.
mkdir -p \
    "$(dirname "$CONFIG_FILE")" \
    "$(dirname "$DATABASE_PATH")" \
    "$DOWNLOAD_ROOT" \
    "$KEYRING_DATA_HOME" \
    "$KEYRING_CONFIG_HOME"

# Seed a default config.yml on first run (mirrors config/config.yml.default).
if [ ! -f "$CONFIG_FILE" ] && [ -f /app/config/config.yml.default ]; then
    cp /app/config/config.yml.default "$CONFIG_FILE"
    echo "[entrypoint] Seeded default config at $CONFIG_FILE"
fi

# The UI fetches /config.json at startup for the API base URL. Regenerate it
# on every boot so it always matches how this container is being served,
# while still allowing an override (e.g. the API is exposed on a different
# host/port than the UI) via the API_URL env var.
cat > /usr/share/nginx/html/config.json <<EOF
{"API_URL": "${API_URL:-/api}"}
EOF

run_supervised() {
    echo "[entrypoint] Starting WireLoft backend on 127.0.0.1:5001"
    backend-api run --host 127.0.0.1 --port 5001 &
    backend_pid=$!

    echo "[entrypoint] Starting nginx on :80 (UI + /api proxy)"
    nginx -g 'daemon off;' &
    nginx_pid=$!

    shutdown() {
        trap - TERM INT
        kill -TERM "$backend_pid" "$nginx_pid" 2>/dev/null || true
        wait "$backend_pid" "$nginx_pid" 2>/dev/null || true
    }
    trap shutdown TERM INT

    # If either process exits, tear the other down and stop the container so
    # Docker's restart policy can bring it back up cleanly.
    wait -n
    exit_code=$?
    shutdown
    exit "$exit_code"
}

if [ "$#" -eq 0 ]; then
    run_supervised
else
    # Escape hatch for one-off maintenance, e.g.:
    #   docker compose run --rm wireloft backend-api db seed
    exec "$@"
fi
