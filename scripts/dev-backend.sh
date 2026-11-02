#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x backend/.venv/bin/python ]; then
  echo "Backend environment is missing. Set it up explicitly with:"
  echo "  python3 -m venv backend/.venv"
  echo "  backend/.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi
if ! backend/.venv/bin/python -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo "FastAPI or Uvicorn is missing from backend/.venv. Install declared dependencies explicitly:"
  echo "  backend/.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi
exec backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8787 --reload
