#!/bin/bash
set -u
plugin_runtime="$HOME/.local/share/tvlk-ai-router-plugin/runtime"
hook_directory=$(cd -- "$(dirname -- "$0")" && pwd) || exit 0
[[ -x "$plugin_runtime/.venv/bin/python" ]] || exit 0
"$plugin_runtime/.venv/bin/python" -I "$hook_directory/router.py" 2>/dev/null || true
