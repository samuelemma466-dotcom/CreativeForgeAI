#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x backend/.venv/bin/python ]; then
  echo "Backend environment is missing. See README.md for the explicit setup commands."
  exit 1
fi
if [ ! -d frontend/node_modules ]; then
  echo "Frontend dependencies are missing. See README.md for the explicit setup commands."
  exit 1
fi

BACKEND_PID=""
cleanup() {
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill -TERM "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if curl --silent --fail http://127.0.0.1:8787/api/health >/dev/null; then
  echo "Reusing the healthy API at http://127.0.0.1:8787."
else
  echo "Starting FastAPI at http://127.0.0.1:8787..."
  ./scripts/dev-backend.sh &
  BACKEND_PID=$!
  ready=0
  for _ in $(seq 1 40); do
    if curl --silent --fail http://127.0.0.1:8787/api/health >/dev/null; then
      ready=1
      break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "Backend exited before becoming healthy."
      wait "$BACKEND_PID" || true
      exit 1
    fi
    sleep 1
  done
  if [ "$ready" -ne 1 ]; then
    echo "Backend did not become healthy within 40 seconds."
    exit 1
  fi
fi

echo "Starting CreativeForge AI at http://127.0.0.1:5173. Press Ctrl+C to stop."
./scripts/dev-frontend.sh
