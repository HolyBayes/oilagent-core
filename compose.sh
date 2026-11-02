#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f workspace/container.env ]; then
    echo 'Run ./run.sh first to build the pinned executor image.' >&2
    exit 1
fi
export LOCAL_UID="$(id -u)"
export LOCAL_GID="$(id -g)"
exec docker compose --env-file .env --env-file workspace/container.env "$@"
