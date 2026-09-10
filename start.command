#!/usr/bin/env bash
cd "$(dirname "$0")"

# Open the browser a few seconds after the server starts (macOS convenience).
(
  sleep 6
  if command -v open >/dev/null 2>&1; then
    open "http://localhost:${PORT:-8501}" || true
  fi
) &

exec bash start.sh
