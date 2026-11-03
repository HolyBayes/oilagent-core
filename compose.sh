#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f workspace/container.env ]; then
    echo 'Run ./run.sh first to build the pinned executor image.' >&2
    exit 1
fi
export LOCAL_UID="$(id -u)"
export LOCAL_GID="$(id -g)"
if [ -f workspace/submodules.compose.json ]; then
    exec docker compose -f compose.yaml -f workspace/submodules.compose.json \
        --env-file .env --env-file workspace/container.env "$@"
fi
exec docker compose --env-file .env --env-file workspace/container.env "$@"
