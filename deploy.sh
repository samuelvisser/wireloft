#!/usr/bin/env bash
# Build the WireLoft image and push it to GitHub Container Registry.
#
# Usage:
#   ./deploy.sh [--tag-level main|pre-release|develop|test] [tag ...]
#   Positional tags are added to the selected/inferred tag level.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE_NAME="wireloft"
REGISTRY="ghcr.io"
GHCR_USER="${GHCR_USER:-samuelvisser}"
CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
TAG_LEVEL=""
EXPLICIT_TAGS=()

while [ "$#" -gt 0 ]; do
    case "$1" in
        --tag-level)
            if [ "$#" -lt 2 ]; then
                echo "--tag-level requires one of: main, pre-release, develop, test." >&2
                exit 2
            fi
            TAG_LEVEL="$2"
            shift 2
            ;;
        --tag-level=*)
            TAG_LEVEL="${1#*=}"
            shift
            ;;
        --)
            shift
            EXPLICIT_TAGS+=("$@")
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
        *)
            EXPLICIT_TAGS+=("$1")
            shift
            ;;
    esac
done

IMAGE_VERSION="${WIRELOFT_VERSION:-development}"
if [ "${#EXPLICIT_TAGS[@]}" -gt 0 ] && [ -z "${WIRELOFT_VERSION:-}" ]; then
    IMAGE_VERSION="${EXPLICIT_TAGS[0]}"
fi

append_tag() {
    local candidate="$1"
    local existing

    if [ "${#TAGS[@]}" -gt 0 ]; then
        for existing in "${TAGS[@]}"; do
            if [ "$existing" = "$candidate" ]; then
                return
            fi
        done
    fi

    TAGS+=("$candidate")
}

add_tag_level() {
    local level="$1"

    case "$level" in
        main)
            append_tag "latest"
            append_tag "pre-release"
            append_tag "develop"
            append_tag "test"
            ;;
        pre-release)
            append_tag "pre-release"
            append_tag "develop"
            append_tag "test"
            ;;
        develop)
            append_tag "develop"
            append_tag "test"
            ;;
        test)
            append_tag "test"
            ;;
        *)
            echo "Invalid tag level '$level'. Expected one of: main, pre-release, develop, test." >&2
            exit 2
            ;;
    esac
}

TAGS=()

if [ -n "$TAG_LEVEL" ]; then
    add_tag_level "$TAG_LEVEL"
elif [ "${#EXPLICIT_TAGS[@]}" -eq 0 ]; then
    case "$CURRENT_BRANCH" in
        main)
            add_tag_level "main"
            ;;
        pre-release/*)
            add_tag_level "pre-release"
            ;;
        develop)
            add_tag_level "develop"
            ;;
        *)
            add_tag_level "test"
            ;;
    esac
fi

if [ "${#EXPLICIT_TAGS[@]}" -gt 0 ]; then
    for explicit_tag in "${EXPLICIT_TAGS[@]}"; do
        append_tag "$explicit_tag"
    done
fi

GIT_REVISION="$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"

FULL_IMAGE="$REGISTRY/$GHCR_USER/$IMAGE_NAME"
TOKEN_FILE="${GHCR_TOKEN_FILE:-$HOME/.config/wireloft/ghcr_token}"
NPMRC="ui/.npmrc"

ensure_docker_running() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker CLI not found. Install Docker Desktop before deploying." >&2
        exit 1
    fi

    if docker info >/dev/null 2>&1; then
        return
    fi

    echo "Docker is not running. Starting Docker Desktop..."

    if docker desktop --help >/dev/null 2>&1; then
        if docker desktop start --timeout 120 >/dev/null 2>&1 \
            && docker info >/dev/null 2>&1; then
            return
        fi
    fi

    if [ "$(uname -s)" != "Darwin" ] || ! command -v open >/dev/null 2>&1; then
        echo "Docker is not running and Docker Desktop could not be started automatically." >&2
        exit 1
    fi

    if ! open -g -a Docker; then
        echo "Could not start Docker Desktop." >&2
        exit 1
    fi

    local deadline=$((SECONDS + 120))
    while [ "$SECONDS" -lt "$deadline" ]; do
        if docker info >/dev/null 2>&1; then
            return
        fi
        sleep 2
    done

    echo "Docker Desktop started, but the Docker daemon did not become available." >&2
    exit 1
}

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

ensure_docker_running
resolve_token

echo "Building $FULL_IMAGE with Font Awesome Pro icons for tags: ${TAGS[*]} ..."
docker build \
    -f .docker/Dockerfile \
    --build-arg WIRELOFT_PRO_ICONS=true \
    --build-arg WIRELOFT_VERSION="$IMAGE_VERSION" \
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
