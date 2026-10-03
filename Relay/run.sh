#!/usr/bin/env bash
# Relay — lokalne uruchomienie całej aplikacji (backend + frontend).
#
#   ./run.sh              # start z auto-reloadem na http://127.0.0.1:8000
#   PORT=9000 ./run.sh    # inny port
#   NO_RELOAD=1 ./run.sh  # bez auto-reloadu
#
# `uv run` sam utworzy środowisko i zainstaluje zależności z pyproject.toml.
set -euo pipefail
cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

RELOAD_ARGS=(--reload --reload-dir app --reload-dir web)
if [[ "${NO_RELOAD:-0}" == "1" ]]; then
  RELOAD_ARGS=()
fi

echo "Relay → http://${HOST}:${PORT}"
exec uv run uvicorn app.main:app \
  --host "$HOST" --port "$PORT" \
  "${RELOAD_ARGS[@]}" "$@"
