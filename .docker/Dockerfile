# syntax=docker/dockerfile:1

########################################
# 1) Build the React UI (Vite + TS)
########################################
FROM node:22-alpine AS ui-build

WORKDIR /ui

ARG WIRELOFT_PRO_ICONS=false

COPY ui/package.json ui/package-lock.json ./

# Keep npm's package download cache independently of Docker's normal layer cache
RUN --mount=type=secret,id=npmrc,target=/ui/.npmrc,required=false \
    --mount=type=cache,id=wireloft-npm,target=/root/.npm,sharing=locked \
    if [ "$WIRELOFT_PRO_ICONS" = "true" ]; then \
        npm ci \
            --include=optional \
            --prefer-offline \
            --no-audit \
            --no-fund; \
    else \
        npm ci \
            --registry=https://registry.npmjs.org \
            --prefer-offline \
            --no-audit \
            --no-fund; \
    fi

COPY ui/ ./

RUN if [ "$WIRELOFT_PRO_ICONS" = "true" ]; then \
        npm run build:pro-icons; \
    else \
        npm run build; \
    fi


########################################
# 2) Backend + runtime image
########################################
FROM python:3.13-slim AS runtime

# ffmpeg -> remuxing downloaded video into .mp4
# nginx  -> serves the built UI and reverse-proxies /api/* to the backend
# tzdata -> lets TZ select a real timezone
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        nginx \
        tzdata \
        bash \
    && rm -rf /var/lib/apt/lists/*

# uv: reproducible installs straight from uv.lock
RUN pip install --no-cache-dir --root-user-action=ignore uv

WORKDIR /app

# Use the Python interpreter already supplied by python:3.13-slim.
ENV UV_PYTHON_PREFERENCE=only-system \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

# Workspace packages are installed editable and therefore need their source
# trees present when uv sync runs.
COPY server ./server

# Preserve uv's download/build cache independently of Docker's normal layer cache
RUN --mount=type=cache,id=wireloft-uv,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev

# Default config seed, copied into the /config volume on first run if missing.
COPY config/config.yml.default ./config/config.yml.default

# Built UI static assets.
COPY --from=ui-build /ui/dist /usr/share/nginx/html

# nginx: single entrypoint on :80 serving the UI and proxying /api to uvicorn.
COPY .docker/app/nginx.conf /etc/nginx/conf.d/default.conf

RUN rm -f /etc/nginx/sites-enabled/default

COPY .docker/app/scripts/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    TZ=UTC \
    WL_CONFIG_FILE=/config/config.yml \
    WL_DATABASE_PATH=/config/wireloft.db \
    PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring \
    XDG_DATA_HOME=/config/keyring/data \
    XDG_CONFIG_HOME=/config/keyring/config

# OpenContainers metadata.
ARG WIRELOFT_VERSION=development
ARG WIRELOFT_REVISION=unknown

LABEL org.opencontainers.image.title="WireLoft" \
      org.opencontainers.image.source="https://github.com/samuelvisser/wireloft" \
      org.opencontainers.image.version="${WIRELOFT_VERSION}" \
      org.opencontainers.image.revision="${WIRELOFT_REVISION}"

VOLUME ["/config", "/downloads"]

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]