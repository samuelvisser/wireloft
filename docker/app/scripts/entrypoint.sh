#!/usr/bin/env sh
set -e

# TODO boot docker container

# Hand off to CMD (i.e. cron -f)
exec "$@"
