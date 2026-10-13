#!/bin/bash
set -euo pipefail
plugin_directory=$(cd -- "$(dirname -- "$0")/.." && pwd)
plugin_runtime="$HOME/.local/share/tvlk-ai-router-plugin/runtime"
if [[ "${1:-}" == "setup" ]]; then
  if command -v python3 >/dev/null 2>&1 && python3 -I -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    printf 'Quit Codex/ChatGPT, then run in Terminal: bash %q --python %q\n' "$plugin_directory/install.sh" "$(command -v python3)"
  else
    printf 'Python 3.11 or newer is required. Choose an approved interpreter, quit Codex/ChatGPT, then run: bash %q --python /path/to/python3\n' "$plugin_directory/install.sh"
  fi
  exit 0
fi
[[ -x "$plugin_runtime/tvlk-ai-router" ]] || { echo 'Setup is required. Invoke tvlk-ai-router setup first.' >&2; exit 4; }
[[ "$("$plugin_runtime/tvlk-ai-router" --version)" == 'TVLK-OpenAI-Router 0.5.0' ]] || { echo 'The cached plugin and installed runtime versions differ. Run setup to update the runtime. The durable recovery command remains available.' >&2; exit 4; }
[[ $# -gt 0 ]] || set -- help
exec "$plugin_runtime/tvlk-ai-router" chat "$@"
