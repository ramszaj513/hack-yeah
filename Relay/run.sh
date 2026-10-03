#!/usr/bin/env bash
# Relay — run the whole application locally (backend + frontend).
#
#   ./run.sh              # start with auto-reload at http://127.0.0.1:8000
#   PORT=9000 ./run.sh    # use another port
#   NO_RELOAD=1 ./run.sh  # disable auto-reload
#
# `uv run` creates the environment and installs dependencies from pyproject.toml.
set -euo pipefail
cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

RELOAD_ARGS=(--reload --reload-dir app --reload-dir web)
if [[ "${NO_RELOAD:-0}" == "1" ]]; then
  RELOAD_ARGS=()
fi

echo "Relay -> http://${HOST}:${PORT}"
exec uv run uvicorn app.main:app \
  --host "$HOST" --port "$PORT" \
  "${RELOAD_ARGS[@]}" "$@"
