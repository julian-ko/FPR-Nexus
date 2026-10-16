"""Read-only context injection, fail closed when session identity is ambiguous."""
import json
import os
import sys
import subprocess
import shlex
from pathlib import Path


def context(payload, runtime, version=None):
    event = payload.get("hook_event_name")
    if event not in ("SessionStart", "UserPromptSubmit"):
        return None
    if payload.get("agent_role") or payload.get("subagent_type") or payload.get("parent_session_id"):
        return None
    os.environ["TVLK_ROUTER_SHELL_ROOT"] = str(runtime)
    os.environ["TVLK_ROUTER_BACKEND"] = "plugin"
    source = runtime / "src"
    if (runtime / "active.json").exists():
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from runtime import selected_source
        source = selected_source(runtime)
    sys.path.insert(0, str(source))
    from tvlk_ai_router import __version__
    from tvlk_ai_router.manager import Manager
    from tvlk_ai_router.config import digest, routing_block
    if version is not None and __version__ != version:
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
    from tvlk_ai_router.updates import check
    policy = check(manager.data.parent / "fpr-nexus-history")
    if policy["status"] == "required":
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext":
                "FPR Nexus requires an upgrade. Do not initiate Nexus automatic routing. Tell the user to refresh FPR Nexus in Codex and run tvlk-ai-router update prepare. Direct Codex use and recovery remain available."}}
    text = routing_block(config)
    recorder = shlex.join([str(runtime / "tvlk-ai-router"), "chat", "record-route",
                          "--transcript", str(transcript), "--session-id", meta["id"]])
    text += ("\nBefore substantive work, record the routing choice once for the current turn using local execution tools: "
             + recorder + " --category <coding|writing|product|analysis|unknown> --mode <delegated|direct> "
             "--reason <code_change|text_edit|product_design|complex_analysis|user_choice|simple_task|mixed_task|management|unknown>. "
             "Choose from the current request, not the model name. Use direct for work you perform yourself, including management. "
             "This saves only IDs and fixed labels locally. A changed choice may be recorded again; identical retries are deduplicated. "
             "Never record raw prompts or a free-text reason. Selection does not prove execution; child roles and parent links are collected separately. "
             "If recording fails, do not invent a turn ID, retry in a loop or block the task; state that attribution is missing.\n")
    if policy["status"] in ("available", "scheduled") and event == "SessionStart":
        text += "\nFPR Nexus update " + policy["latest"] + " is available. Mention tvlk-ai-router update check to the user."
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def main():
    try:
        payload = json.load(sys.stdin)
        runtime = Path.home() / ".local/share/tvlk-ai-router-plugin/runtime"
        event = payload.get("hook_event_name")
        if event in ("SessionStart", "UserPromptSubmit") and (runtime / "active.json").exists():
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
                from runtime import sync
                sync(Path(__file__).resolve().parents[1], runtime)
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                pass  # A failed update must not replace the verified installed release.
        if event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            try:
                subprocess.Popen([str(runtime / ".venv/bin/python"), "-I", str(Path(__file__).resolve().parents[1] / "scripts/collect.py"), *(["--final"] if event in ("Stop", "SessionEnd") else [])],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                pass
        value = context(payload, runtime)
        if value:
            print(json.dumps(value))
        elif event == "Stop":
            print("{}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
