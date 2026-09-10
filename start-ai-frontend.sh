#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating virtual environment .venv ..."
  "${PYTHON_BIN:-python3}" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import streamlit" >/dev/null 2>&1; then
  echo "Installing dependencies (first run only) ..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

echo "Starting the EAR AI Assistant on http://localhost:${PORT:-8502}"
exec streamlit run app/ai_main.py \
  --server.headless true \
  --server.showEmailPrompt false \
  --server.port "${PORT:-8502}" \
  --browser.gatherUsageStats false
