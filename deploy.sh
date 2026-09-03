#!/usr/bin/env bash
# Build the WireLoft image and push it to GitHub Container Registry.
#
# Usage:
#   ./deploy.sh [tag ...]    # explicit tags, or defaults by branch when omitted

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE_NAME="wireloft"
REGISTRY="ghcr.io"
GHCR_USER="${GHCR_USER:-samuelvisser}"
CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
MANUAL_TAGS=("$@")
APP_VERSION="$(python3 - <<'PY_VERSION'
import tomllib
from pathlib import Path

with Path("pyproject.toml").open("rb") as file:
    print(tomllib.load(file)["project"]["version"])
PY_VERSION
)"
GIT_REVISION="$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"

if [ "${#MANUAL_TAGS[@]}" -gt 0 ]; then
    TAG="${MANUAL_TAGS[0]}"
    TAGS=("${MANUAL_TAGS[@]}")
else
    case "$CURRENT_BRANCH" in
        main)
            TAG="latest"
            TAGS=("latest" "develop" "test")
            ;;
        develop)
            TAG="develop"
            TAGS=("develop" "test")
            ;;
        *)
            TAG="test"
            TAGS=("test")
            ;;
    esac
fi

FULL_IMAGE="$REGISTRY/$GHCR_USER/$IMAGE_NAME"
TOKEN_FILE="${GHCR_TOKEN_FILE:-$HOME/.config/wireloft/ghcr_token}"
NPMRC="ui/.npmrc"

resolve_token() {
    if [ -n "${GHCR_TOKEN:-}" ]; then
        return
    fi

    if [ -f "$TOKEN_FILE" ]; then
        GHCR_TOKEN="$(cat "$TOKEN_FILE")"
        if [ -n "$GHCR_TOKEN" ]; then
            echo "Using ghcr.io token from $TOKEN_FILE." >&2
            return
        fi
    fi

    printf 'No ghcr.io token found. Paste a GitHub PAT with "write:packages" scope: ' >&2
    read -r -s GHCR_TOKEN
    echo >&2
    if [ -z "$GHCR_TOKEN" ]; then
        echo "No token provided, aborting." >&2
        exit 1
    fi

    read -r -p "Save this token to $TOKEN_FILE for next time? [Y/n] " save_choice >&2
    case "${save_choice:-Y}" in
        [nN]*) ;;
        *)
            mkdir -p "$(dirname "$TOKEN_FILE")"
            ( umask 077; printf '%s' "$GHCR_TOKEN" > "$TOKEN_FILE" )
            chmod 600 "$TOKEN_FILE"
            echo "Saved to $TOKEN_FILE (readable by your user only)." >&2
            ;;
    esac
}

if [ ! -f "$NPMRC" ]; then
    echo "Missing $NPMRC (Font Awesome Pro credentials are required for release builds)." >&2
    echo "Normal local and Docker builds do not require this file." >&2
    exit 1
fi

resolve_token

echo "Building $FULL_IMAGE:$TAG with Font Awesome Pro icons ..."
docker build \
    -f .docker/Dockerfile \
    --build-arg WIRELOFT_PRO_ICONS=true \
    --build-arg WIRELOFT_VERSION="$APP_VERSION" \
    --build-arg WIRELOFT_REVISION="$GIT_REVISION" \
    --secret id=npmrc,src="$NPMRC" \
    -t "$IMAGE_NAME" \
    .

printf '%s' "$GHCR_TOKEN" | docker login "$REGISTRY" -u "$GHCR_USER" --password-stdin

for push_tag in "${TAGS[@]}"; do
    docker tag "$IMAGE_NAME" "$FULL_IMAGE:$push_tag"
    docker push "$FULL_IMAGE:$push_tag"
    echo "Pushed $FULL_IMAGE:$push_tag"
done
