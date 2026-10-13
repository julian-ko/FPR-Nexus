#!/bin/bash
set -euo pipefail
[[ $# -eq 1 ]] || { echo "Usage: bash manage.sh <pending-request-id>" >&2; exit 2; }
[[ "$1" =~ ^[a-f0-9]{32}$ ]] || { echo "Error: Invalid request ID." >&2; exit 2; }
runtime_directory=$(cd -- "$(dirname -- "$0")" && pwd)
exec "$runtime_directory/.venv/bin/python" -I "$runtime_directory/runner.py" desktop perform --request-id "$1"
