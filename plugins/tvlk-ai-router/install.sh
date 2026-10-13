#!/bin/bash
set -euo pipefail
installer_python=python3
if [[ "${1:-}" == "--python" ]]; then
  [[ $# -ge 2 ]] || { echo "Error: --python requires an interpreter path." >&2; exit 2; }
  installer_python=$2
  shift 2
fi
command -v "$installer_python" >/dev/null 2>&1 || { echo "Error: Python 3.11 or newer is required. Use --python /path/to/python3." >&2; exit 2; }
"$installer_python" -I -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 2)' || { echo "Error: Python 3.11 or newer is required." >&2; exit 2; }
installer_directory=$(cd -- "$(dirname -- "$0")" && pwd)
exec "$installer_python" -I "$installer_directory/scripts/install.py" "$@"
