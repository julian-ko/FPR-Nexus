"""Client detection shared by the setup window and the configuration write guard."""
import os
import subprocess
from pathlib import Path


def running_clients(include_router=False):
    try:
        listing = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True,
                                 text=True, check=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Cannot check running applications; setup cannot safely continue") from exc
    blocked = []
    for row in listing.splitlines():
        fields = row.strip().split(None, 1)
        if len(fields) != 2 or fields[0] == str(os.getpid()):
            continue
        name = Path(fields[1]).name.lower()
        old_router = include_router and "/TVLK-OpenAI-Router.app/Contents/MacOS/" in fields[1]
        if old_router or name in {"codex", "codex-cli", "codexcli", "chatgpt", "codex app"} or name.startswith(("chatgpt helper", "codex helper")):
            blocked.append(fields[0] + ":" + name)
    return blocked
