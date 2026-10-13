#!/bin/bash
# Shared by chat setup and the direct installer; never installs Python.
tvlk_find_python() {
  local candidate resolved version
  if [[ -n "${1:-${TVLK_ROUTER_PYTHON:-}}" ]]; then
    set -- "${1:-$TVLK_ROUTER_PYTHON}"
  else
    set -- python3 python3.14 python3.13 python3.12 python3.11 \
      "$HOME/.local/share/tvlk-ai-router-plugin/runtime/.venv/bin/python" \
      /opt/homebrew/bin/python3 /usr/local/bin/python3
    for version in 14 13 12 11; do
      set -- "$@" "/opt/homebrew/opt/python@3.$version/bin/python3.$version" \
        "/usr/local/opt/python@3.$version/bin/python3.$version"
    done
    set -- "$@" \
      /Library/Frameworks/Python.framework/Versions/{3.14,3.13,3.12,3.11}/bin/python3 \
      "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
  fi
  for candidate in "$@"; do
    resolved=$(command -v "$candidate" 2>/dev/null) || continue
    if "$resolved" -I -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  echo 'No usable Python 3.11+ with venv and ensurepip was found. Use setup --python /absolute/path/to/python3 or ask IT for an approved Python installation, then retry setup.' >&2
  return 4
}
