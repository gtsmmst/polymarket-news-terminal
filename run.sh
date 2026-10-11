#!/usr/bin/env bash
# Start the Polymarket News Terminal on http://127.0.0.1:8001
# Creates a local virtualenv on first run and installs dependencies.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtualenv in .venv ..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -q -r requirements.txt

echo "==================================================="
echo "  Polymarket News Terminal"
echo "  Open in browser:  http://127.0.0.1:8001"
echo "  First cycle pulls markets + news (~30-60 s),"
echo "  then press 'Refresh News + Score' or just wait."
echo "  Stop with Ctrl+C"
echo "==================================================="

exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8001}"
