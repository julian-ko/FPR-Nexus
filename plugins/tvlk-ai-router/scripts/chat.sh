#!/bin/bash
set -euo pipefail
plugin_directory=$(cd -- "$(dirname -- "$0")/.." && pwd)
plugin_runtime="$HOME/.local/share/tvlk-ai-router-plugin/runtime"
if [[ "${1:-}" == "setup" ]]; then
  if command -v python3 >/dev/null 2>&1 && python3 -I -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    exec python3 -I "$plugin_directory/scripts/setup.py" "${@:2}"
  else
    printf 'Python 3.11 or newer is required. Choose an approved interpreter, quit Codex/ChatGPT, then run: bash %q --python /path/to/python3\n' "$plugin_directory/install.sh" >&2
    exit 4
  fi
  exit 0
fi
[[ -x "$plugin_runtime/tvlk-ai-router" ]] || { echo 'Setup is required. Invoke tvlk-ai-router setup first.' >&2; exit 4; }
[[ "$("$plugin_runtime/tvlk-ai-router" --version)" == 'TVLK-OpenAI-Router 1.0.1' ]] || { echo 'The cached plugin and installed runtime versions differ. Run setup to update the runtime. The durable recovery command remains available.' >&2; exit 4; }
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
