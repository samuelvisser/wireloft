########################################
# 1) Build the React UI (Vite + TS)
########################################
FROM node:22-alpine AS ui-build
WORKDIR /ui

COPY ui/package.json ui/package-lock.json ./
RUN npm ci

COPY ui/ ./
RUN npm run build

########################################
# 2) Backend + runtime image
########################################
FROM python:3.13-slim AS runtime

# ffmpeg   -> remuxing downloaded video into .mp4 (downloadSettings.remuxVideoToMp4)
# nginx    -> serves the built UI and reverse-proxies /api/* to the backend
# tzdata   -> lets the TZ env var select a real timezone
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg nginx tzdata bash \
    && rm -rf /var/lib/apt/lists/*

# uv: reproducible installs straight from uv.lock
RUN pip install --no-cache-dir --root-user-action=ignore uv

WORKDIR /app

# Use the interpreter already on PATH (matches requires-python 3.13) instead of
# having uv fetch its own, and keep the venv at a known, fixed location.
ENV UV_PYTHON_PREFERENCE=only-system \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./
COPY server ./server
# Workspace members are installed editable (the default), which is required:
# every package's config.py derives PROJECT_ROOT from its own file location by
# walking up a fixed number of parents, assuming the server/<pkg>/src/<pkg>/
# source layout stays on disk. A non-editable install would flatten that
# layout and break the derived path.
RUN uv sync --frozen --no-dev

# Default config seed, copied into the /config volume on first run if missing
COPY config/config.yml.default ./config/config.yml.default

# Built UI static assets
COPY --from=ui-build /ui/dist /usr/share/nginx/html

# nginx: single entrypoint on :80 serving the UI and proxying /api to uvicorn
COPY docker/app/nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/sites-enabled/default

COPY docker/app/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    TZ=UTC \
    # Persistent app state (config, SQLite DB, session secret key) lives on
    # the /config volume; downloaded media lives on the /downloads volume.
    # The download root and the secret-key fallback path are set inside
    # config/config.yml.default instead of as env vars here -- see the
    # comment at the top of that file for why (nested-settings overrides via
    # env vars must supply every field of the block, not just one).
    WL_CONFIG_FILE=/config/config.yml \
    WL_DATABASE_PATH=/config/wireloft.db \
    # DailyWire login tokens are stored via the `keyring` package. Containers
    # have no OS keychain/D-Bus session, so keyring already falls back to the
    # file-based keyrings.alt backend automatically -- these two env vars just
    # make that explicit and point its storage at the /config volume so a
    # login survives container recreation instead of living under /root.
    PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring \
    XDG_DATA_HOME=/config/keyring/data \
    XDG_CONFIG_HOME=/config/keyring/config

VOLUME ["/config", "/downloads"]
EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
