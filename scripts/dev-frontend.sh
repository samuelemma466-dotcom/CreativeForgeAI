#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d frontend/node_modules ]; then
  echo "Frontend dependencies are missing. Install the declared packages explicitly with:"
  echo "  npm --prefix frontend install"
  exit 1
fi
exec npm --prefix frontend run dev -- --strictPort
