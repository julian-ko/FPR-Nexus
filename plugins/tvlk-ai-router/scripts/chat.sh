#!/bin/bash
set -euo pipefail
plugin_directory=$(cd -- "$(dirname -- "$0")/.." && pwd)
plugin_runtime="$HOME/.local/share/tvlk-ai-router-plugin/runtime"
if [[ "${1:-}" == "update" ]]; then
  shift
  source "$plugin_directory/scripts/python.sh"
  installer_python=$(tvlk_find_python "${TVLK_ROUTER_PYTHON:-}")
  exec "$installer_python" -I "$plugin_directory/scripts/update.py" "$@"
fi
if [[ "${1:-}" == "setup" ]]; then
  shift
  installer_python=${TVLK_ROUTER_PYTHON:-}
  if [[ "${1:-}" == "--python" ]]; then
    [[ $# -ge 2 && -n "$2" ]] || { echo 'Error: --python requires an interpreter path.' >&2; exit 2; }
    installer_python=$2
    shift 2
  fi
  source "$plugin_directory/scripts/python.sh"
  installer_python=$(tvlk_find_python "$installer_python")
  printf 'Using Python: %s\n' "$installer_python"
  exec "$installer_python" -I "$plugin_directory/scripts/setup.py" "$@"
fi
[[ -x "$plugin_runtime/tvlk-ai-router" ]] || { echo 'Setup is required. Invoke tvlk-ai-router setup first.' >&2; exit 4; }
[[ "$("$plugin_runtime/tvlk-ai-router" --version)" == 'FPR Nexus 1.3.0' ]] || { echo 'The cached plugin and installed runtime versions differ. Run setup to update the runtime. The durable recovery command remains available.' >&2; exit 4; }
[[ $# -gt 0 ]] || set -- help
case "$1" in
  config)
    if [[ "${2:-}" == "show" ]]; then set -- show
    elif [[ "${2:-}" == "validate" || "${2:-}" == "example" ]]; then exec "$plugin_runtime/tvlk-ai-router" "$@"
    fi ;;
  backup) [[ "${2:-}" == "list" ]] && set -- backups ;;
  apply|enable|disable) set -- request "$1" ;;
  restore) [[ $# -eq 2 ]] || { echo 'Usage: restore <backup-id>' >&2; exit 2; }; set -- request restore --backup-id "$2" ;;
esac
exec "$plugin_runtime/tvlk-ai-router" chat "$@"
