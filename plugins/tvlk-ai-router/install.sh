#!/bin/bash
set -euo pipefail
installer_python=${TVLK_ROUTER_PYTHON:-}
if [[ "${1:-}" == "--python" ]]; then
  [[ $# -ge 2 && -n "$2" ]] || { echo "Error: --python requires an interpreter path." >&2; exit 2; }
  installer_python=$2
  shift 2
fi
installer_directory=$(cd -- "$(dirname -- "$0")" && pwd)
source "$installer_directory/scripts/python.sh"
installer_python=$(tvlk_find_python "$installer_python") || exit 2
printf 'Using Python: %s\n' "$installer_python"
exec "$installer_python" -I "$installer_directory/scripts/install.py" "$@"
