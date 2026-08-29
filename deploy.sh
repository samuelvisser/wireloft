#!/usr/bin/env bash
# Build the WireLoft image and push it to GitHub Container Registry.
#
# Usage:
#   ./deploy.sh [tag]        # defaults by branch: main=latest, develop=develop, other=test

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE_NAME="wireloft"
REGISTRY="ghcr.io"
GHCR_USER="${GHCR_USER:-samuelvisser}"
CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
MANUAL_TAG="${1:-}"

if [ -n "$MANUAL_TAG" ]; then
    TAG="$MANUAL_TAG"
    TAGS=("$TAG")
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
    echo "Missing $NPMRC (Font Awesome Pro credentials needed to build the UI)." >&2
    echo "See the 'Running with Docker' section in README.md." >&2
    exit 1
fi

resolve_token

echo "Building $FULL_IMAGE:$TAG ..."
docker build \
    -f .docker/Dockerfile \
    --secret id=npmrc,src="$NPMRC" \
    -t "$IMAGE_NAME" \
    .

printf '%s' "$GHCR_TOKEN" | docker login "$REGISTRY" -u "$GHCR_USER" --password-stdin

for push_tag in "${TAGS[@]}"; do
    docker tag "$IMAGE_NAME" "$FULL_IMAGE:$push_tag"
    docker push "$FULL_IMAGE:$push_tag"
    echo "Pushed $FULL_IMAGE:$push_tag"
done
