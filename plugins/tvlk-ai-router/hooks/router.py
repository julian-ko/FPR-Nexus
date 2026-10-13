"""Read-only context injection, fail closed when session identity is ambiguous."""
import json
import os
import sys
from pathlib import Path


def context(payload, runtime, version="1.0.3"):
    event = payload.get("hook_event_name")
    if event not in ("SessionStart", "UserPromptSubmit"):
        return None
    if payload.get("agent_role") or payload.get("subagent_type") or payload.get("parent_session_id"):
        return None
    os.environ["TVLK_ROUTER_SHELL_ROOT"] = str(runtime)
    os.environ["TVLK_ROUTER_BACKEND"] = "plugin"
    sys.path.insert(0, str(runtime / "src"))
    from tvlk_ai_router import __version__
    from tvlk_ai_router.manager import Manager
    from tvlk_ai_router.config import digest, routing_block
    if __version__ != version:
        return None
    data = Path.home() / ".local/share/tvlk-ai-router/state.json"
    if not data.is_file() or data.is_symlink():
        return None
    state = json.loads(data.read_text())
    if state.get("installation_backend") != "plugin" or state.get("status") != "enabled":
        return None
    targets = state.get("targets", [])
    if len(targets) != 3:
        return None
    manager = Manager(targets[0], targets[1], str(data.parent), targets[2])
    transcript = Path(payload.get("transcript_path", ""))
    if not transcript.is_absolute() or transcript.is_symlink() or any(p.is_symlink() for p in transcript.parents):
        return None
    if not any(transcript.is_relative_to(manager.home / name) for name in ("sessions", "archived_sessions")):
        return None
    with transcript.open(encoding="utf-8") as stream:
        record = json.loads(next(stream))
    meta = record.get("payload", {})
    if record.get("type") != "session_meta" or meta.get("id") != payload.get("session_id"):
        return None
    if meta.get("agent_role") or not isinstance(meta.get("source"), str) or meta.get("source") not in ("cli", "vscode", "desktop", "exec"):
        return None
    raw, config = manager.config()
    if digest(raw) != state.get("applied_config_hash") or manager.drift():
        return None
    text = routing_block(config)
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def main():
    try:
        payload = json.load(sys.stdin)
        runtime = Path.home() / ".local/share/tvlk-ai-router-plugin/runtime"
        value = context(payload, runtime)
        if value:
            print(json.dumps(value))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
