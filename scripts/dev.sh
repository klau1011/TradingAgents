#!/usr/bin/env bash
# Start the web dashboard backend + frontend for local dev.
# Both stop together on Ctrl-C.
set -euo pipefail
cd "$(dirname "$0")/.."
PATH="$PWD/.venv/bin:$PATH"

trap 'kill 0' EXIT

uvicorn web.backend.app:app --reload --port 8000 &
(cd web/frontend && npm run dev) &

wait
