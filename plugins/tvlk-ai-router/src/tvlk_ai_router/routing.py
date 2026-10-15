"""Save bounded routing decisions, never task text or tool output."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import RouterError

TASKS = ("coding", "writing", "product", "analysis", "unknown")
MODES = ("delegated", "direct")
REASONS = ("code_change", "text_edit", "product_design", "complex_analysis",
           "user_choice", "simple_task", "mixed_task", "management", "unknown")


def record_route(manager, transcript, session_id, category, mode, reason, now=None):
    from .history import connect
    if category not in TASKS or mode not in MODES or reason not in REASONS:
        raise RouterError("Use a supported task type, mode and reason code", 4)
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise RouterError("Invalid session identity", 4)
    if not manager.state or manager.state.get("status") != "enabled":
        raise RouterError("Routing records require an enabled Nexus installation", 4)
    path = Path(transcript)
    if (not path.is_absolute() or ".." in path.parts or path.is_symlink()
            or any(p.is_symlink() for p in path.parents)
            or not any(path.is_relative_to(manager.home / name) for name in ("sessions", "archived_sessions"))):
        raise RouterError("Routing transcript must be a local Codex journal without symbolic links", 4)
    active, context, context_at, completed = None, {}, None, set()
    with path.open(encoding="utf-8") as stream:
        first = json.loads(next(stream, "{}"))
        meta = first.get("payload", {})
        if (first.get("type") != "session_meta" or meta.get("id") != session_id
                or meta.get("agent_role") or meta.get("source") not in ("cli", "vscode", "desktop", "exec")):
            raise RouterError("Routing records require the matching root session", 4)
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            p = row.get("payload", {})
            if not isinstance(p, dict):
                continue
            if row.get("type") == "turn_context":
                active, context = p.get("turn_id"), p
                context_at = row.get("timestamp")
            elif row.get("type") == "event_msg":
                if p.get("type") == "task_started":
                    active = p.get("turn_id")
                elif p.get("type") in ("task_complete", "task_cancelled", "turn_aborted"):
                    completed.add(p.get("turn_id") or active)
    if (not isinstance(active, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", active)
            or context.get("turn_id") != active or active in completed):
        raise RouterError("No unambiguous active turn; leave routing attribution unknown", 4)
    _, config = manager.config()
    selected = config["agents"].get(category) if mode == "delegated" else config["coordinator"]
    if selected is None:
        raise RouterError("Delegation requires a configured task role", 4)
    body = {"thread_id": session_id, "turn_id": active, "task_type": category, "mode": mode,
            "reason": reason, "selected_model": selected["model"], "selected_effort": selected["reasoning_effort"],
            "selected_role": selected.get("name") if mode == "delegated" else None,
            "evidence": "agent_recorded_selection"}
    ident = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    body["recorded_at"] = (now or datetime.now(timezone.utc)).isoformat()
    source = hashlib.sha256(str(manager.home).encode()).hexdigest()
    db = connect(manager.data.parent / "fpr-nexus-history")
    try:
        with db:
            db.execute("INSERT OR IGNORE INTO routes VALUES(?,?,?,?,?)", (source, session_id, active, ident, json.dumps(body)))
            from .usage import timestamp
            turn = {"thread_id": session_id, "turn_id": active, "date": (timestamp(context_at) or timestamp(body["recorded_at"])).isoformat(),
                    "model": context.get("model", "unknown"), "reasoning_effort": context.get("effort", "unknown"),
                    "category": "unknown", "status": "started", "token_coverage": "unknown"}
            db.execute("INSERT OR IGNORE INTO turns VALUES(?,?,?,?)", (source, session_id, active, json.dumps(turn)))
    finally:
        db.close()
    return {"status": "recorded", "thread_id": session_id, "turn_id": active,
            "task_type": category, "mode": mode, "reason": reason,
            "note": "Selection recorded; actual child execution is verified separately from journals."}


def attribution(key, row, parents, routes):
    """Keep selected intent separate from observed roles and parent relationships."""
    decisions = routes.get(key, [])
    parent = (row.get("parent_thread_id"), row.get("parent_turn_id"))
    parent_decisions = routes.get(parent, [])
    category = row.get("category", "unknown")
    if category == "unknown" and key in parents:
        category = "coordinator"
    selected = {d["task_type"] for d in decisions}
    task = next(iter(selected)) if len(selected) == 1 else "mixed" if selected else category
    role = row.get("agent_role")
    from .usage import ROLES
    executor = role in ROLES or category in ROLES.values()
    coordinator = key in parents or any(d["mode"] == "delegated" for d in decisions)
    activity = "executor" if executor else "coordinator" if coordinator else "direct" if decisions else "unknown"
    basis = "recorded_agent_role" if executor else "agent_recorded_selection" if decisions else "recorded_parent_link" if key in parents else "unknown"
    return {"task_type": task, "activity": activity, "nexus": executor or coordinator or bool(decisions),
            "attribution_basis": basis, "parent_thread_id": parent[0], "parent_turn_id": parent[1],
            "route_decisions": decisions or parent_decisions,
            "selection_scope": "this_turn" if decisions else "parent_turn" if parent_decisions else "unknown"}
