"""Read-only recognition of a Shell bootstrap that failed before configuration writes."""
import hashlib
import json
import os
from pathlib import Path


# Shipped wrappers in Shell 0.4.1 and 0.4.2; never execute orphaned files.
WRAPPERS = {
    "runner.py": "29dc34a29cc9e2e2705ff38246c4a5d46a5c6a95c4d4724fb25afd7bf8c98fd4",
    "tvlk-ai-router": "d2fcd6d8504b64e5dba85b5bf316b7124baf4c9053c8515169bed615296c3456",
    "manage.sh": "11077c75736e61e90d8d08fa394e105ab7db3efb1c8f387f55c8ee66be763a4d",
}


def recognized_failed_shell():
    home = Path.home()
    data = home / ".local/share/tvlk-ai-router"
    shell = home / ".local/share/tvlk-ai-router-shell/runtime"
    config = home / ".config/tvlk-ai-router"
    codex = Path(os.environ.get("CODEX_HOME", str(home / ".codex"))).expanduser().absolute()
    absent = [data / "state.json", home / "Applications/TVLK-OpenAI-Router.app",
              home / ".agents/skills/tvlk-ai-router"]
    native = [codex / "config.toml", codex / "AGENTS.md", codex / "agents"]
    try:
        for path in [data, shell, config, *absent, *native]:
            if any(p.is_symlink() for p in (path, *path.parents)):
                return False
        if not shell.is_dir() or any(p.exists() for p in absent):
            return False
        if config.exists() and (not config.is_dir() or any(config.iterdir())):
            return False
        if data.exists():
            if not data.is_dir() or any(p.name != "lock" or p.is_symlink() or not p.is_file() or p.stat().st_size for p in data.iterdir()):
                return False
        for path in native[:2]:
            if path.exists() and any(marker in path.read_bytes() for marker in (b"tvlk_ai_route_", b"TVLK-OPENAI-ROUTER")):
                return False
        if native[2].exists() and any(native[2].glob("tvlk_ai_route_*")):
            return False
        if any(p.is_symlink() or p.name not in {".venv", "shell-installation.json", *WRAPPERS} for p in shell.iterdir()):
            return False
        marker = json.loads((shell / "shell-installation.json").read_bytes())
        if marker != {"runtime": str(shell), "distribution": "shell"}:
            return False
        if (shell / ".venv").exists() and not (shell / ".venv").is_dir():
            return False
        for name, sha in WRAPPERS.items():
            path = shell / name
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                return False
        return True
    except (OSError, ValueError):
        return False
