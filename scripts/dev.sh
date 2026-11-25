#!/usr/bin/env bash
# One-command local run without Docker: sets up venv + node_modules on first run,
# then starts the API (:8000) and the web app (:5173). Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

if [ ! -x "$ROOT/backend/.venv/bin/uvicorn" ]; then
  echo "▸ creating Python venv"
  "$PY" -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -q --upgrade pip
  "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements-dev.txt"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "▸ installing frontend dependencies"
  (cd "$ROOT/frontend" && npm ci)
fi

trap 'kill 0' EXIT INT TERM
(cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --port 8000 --reload) &
(cd "$ROOT/frontend" && npm run dev -- --host 127.0.0.1) &
echo "▸ DraftMind AI → http://127.0.0.1:5173  (API http://127.0.0.1:8000/docs)"
wait
