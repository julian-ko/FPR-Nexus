"""Read-only recognition of verified baseline copies from an unfinished first setup."""
import hashlib
import json
import os
import re
from pathlib import Path


def safe(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Recovery paths must not contain symbolic links")
    return path


def baseline(path, codex, shared, config):
    name = path.name.removesuffix(".partial")
    if not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", name) or not safe(path).is_dir():
        return False
    if {p.name for p in path.iterdir()} != {"files", "manifest.json", "COMPLETE"}:
        return False
    if any(not safe(path / name).is_file() for name in ("manifest.json", "COMPLETE")):
        return False
    raw = safe(path / "manifest.json").read_bytes()
    if safe(path / "COMPLETE").read_text().strip() != hashlib.sha256(raw).hexdigest():
        return False
    manifest = json.loads(raw)
    if (manifest.get("schema") != 1 or manifest.get("id") != name
            or manifest.get("reason") != "baseline" or "router_state" not in manifest
            or manifest["router_state"] is not None or manifest.get("codex_home") != str(codex)):
        return False
    roots = [Path(p) for p in manifest["roots"]]
    if not {codex, shared, config} <= set(roots) or any(not p.is_absolute() for p in roots):
        return False
    hashes = set()
    for name, item in manifest["entries"].items():
        source = Path(name)
        if not source.is_absolute() or ".." in source.parts or not any(source == r or source.is_relative_to(r) for r in roots):
            return False
        if item["type"] == "file":
            sha = item["sha256"]
            if not re.fullmatch(r"[a-f0-9]{64}", sha):
                return False
            hashes.add(sha)
    blobs = safe(path / "files")
    if not blobs.is_dir() or {p.name for p in blobs.iterdir()} != hashes:
        return False
    for sha in hashes:
        blob = safe(blobs / sha)
        if not blob.is_file():
            return False
        with blob.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
                return False
    return True


def recognized_failed_plugin(root):
    home = Path.home()
    data = home / ".local/share/tvlk-ai-router"
    config = home / ".config/tvlk-ai-router"
    shared = home / ".agents"
    codex = Path(os.environ.get("CODEX_HOME", str(home / ".codex"))).expanduser().absolute()
    try:
        if root != home / ".local/share/tvlk-ai-router-plugin/runtime":
            return False
        marker = json.loads(safe(root / "shell-installation.json").read_bytes())
        if marker != {"runtime": str(root), "distribution": "plugin"}:
            return False
        # A completed runtime or saved configuration needs recovery, not a fresh install.
        absent = [root / n for n in ("src", "src.old", "active.json", "releases")]
        absent += [shared / "skills/tvlk-ai-router", codex / "skills/tvlk-ai-router"]
        if any(safe(p).exists() for p in absent):
            return False
        if safe(config).exists() and (not config.is_dir() or any(config.iterdir())):
            return False
        for name in ("config.toml", "AGENTS.md", "AGENTS.override.md"):
            p = safe(codex / name)
            if p.exists() and any(m in p.read_bytes() for m in (b"tvlk_ai_route_", b"TVLK-OPENAI-ROUTER")):
                return False
        agents = safe(codex / "agents")
        if agents.exists() and any(agents.glob("tvlk_ai_route_*")):
            return False
        entries = list(safe(data).iterdir())
        if any(safe(p).name not in {"lock", "backups"} for p in entries):
            return False
        lock = data / "lock"
        if lock.exists() and (not lock.is_file() or lock.stat().st_size):
            return False
        store = safe(data / "backups")
        if not store.is_dir():
            return False
        copies = list(store.iterdir())
        return bool(copies) and all(baseline(p, codex, shared, config) for p in copies)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
