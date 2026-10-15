"""Read local execution journals without exporting messages or creating files."""
import json
import hashlib
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from .config import RouterError

FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")
ROLES = {"tvlk_ai_route_" + role: role for role in ("coding", "writing", "product", "analysis")}


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def installation_start(state):
    state = state or {}
    if timestamp(state.get("installed_at")):
        return {"at": state["installed_at"], "source": "installation_transaction", "approximate": False}
    baseline = state.get("baseline", "")
    match = re.match(r"^(\d{8}T\d{6}Z)-", baseline)
    if match:
        try:
            at = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return {"at": at.isoformat(), "source": "legacy_baseline_backup", "approximate": True}
        except ValueError:
            pass
    return {"at": None, "source": "unknown", "approximate": True}


def usage(value):
    if not isinstance(value, dict):
        return None
    # Optional cache/reasoning fields stay unknown; do not add them to input/output.
    if any(type(value.get(k)) is not int or value[k] < 0 for k in ("input_tokens", "output_tokens", "total_tokens")):
        return None
    return {k: value.get(k) if type(value.get(k)) is int and value[k] >= 0 else None for k in FIELDS}


def review(home, state, period="7d", now=None, *, paths=None, include_events=False):
    now = now or datetime.now(timezone.utc)
    start = installation_start(state)
    if period == "since-install":
        since = timestamp(start["at"])
        if since is None:
            raise RouterError("Installation start is unknown; use review 7d or review 30d", 4)
    elif period == "all":
        since = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elif period in ("7d", "30d"):
        since = now - timedelta(days=int(period[:-1]))
    else:
        raise RouterError("Review period must be 7d, 30d or since-install", 4)
    counts = Counter()
    turns, seen_events = {}, set()
    parents = set()
    events = []
    supplied_paths = paths is not None
    paths = list(paths or [])
    for directory in (() if supplied_paths else (home / "sessions", home / "archived_sessions")):
        if directory.is_symlink():
            counts["unreadable_files"] += 1
            continue
        paths.extend(sorted(directory.rglob("*.jsonl")) if directory.exists() else ())
    for path in paths:
        try:
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != home):
                continue
            with path.open(encoding="utf-8") as stream:
                meta = json.loads(next(stream)).get("payload", {})
                if meta.get("agent_role") in ROLES:
                    parent = meta.get("source", {}).get("subagent", {}).get("thread_spawn", {}).get("parent_thread_id")
                    boundary = meta.get("subagent_history_start_ordinal")
                    if isinstance(parent, str) and type(boundary) is int:
                        for ordinal, line in enumerate(stream, 1):
                            if ordinal < boundary:
                                continue
                            try:
                                record = json.loads(line)
                                root_turn = record.get("payload", {}).get("root_turn_id")
                                if record.get("type") == "turn_context" and isinstance(root_turn, str):
                                    parents.add((parent, root_turn))
                            except (ValueError, AttributeError):
                                continue
        except (OSError, ValueError, AttributeError, TypeError, StopIteration):
            pass
    for path in paths:
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != home):
                counts["unreadable_files"] += 1
                continue
            counts["journal_files"] += 1
            meta, context, previous, previous_context = {}, {}, None, None
            active, boundary, excluded = None, 0, False
            reset_epoch = 0
            try:
                stream = path.open(encoding="utf-8", errors="replace")
            except OSError:
                counts["unreadable_files"] += 1
                continue
            with stream:
                for ordinal, line in enumerate(stream):
                    try:
                        record = json.loads(line)
                        p = record.get("payload", {})
                        if not isinstance(p, dict):
                            raise ValueError()
                    except (ValueError, AttributeError):
                        counts["malformed_lines"] += 1
                        continue
                    typ = record.get("type")
                    if typ == "session_meta" and not meta:
                        if not isinstance(p.get("id"), str) or p.get("agent_role") is not None and not isinstance(p["agent_role"], str):
                            counts["malformed_lines"] += 1
                            meta = {"invalid": True}
                            excluded = True
                            continue
                        meta = p
                        source = p.get("source")
                        sub = source.get("subagent", {}) if isinstance(source, dict) else {}
                        excluded = bool(isinstance(sub, dict) and "other" in sub)
                        if excluded:
                            counts["excluded_system_sessions"] += 1
                        value = p.get("subagent_history_start_ordinal", None if sub else 0)
                        if type(value) is int and value >= 0:
                            boundary = value
                        elif sub:
                            excluded = True
                            counts["unknown_history_sessions"] += 1
                    if excluded:
                        continue
                    inherited = ordinal < boundary
                    if inherited:
                        counts["excluded_inherited_events"] += 1
                    if typ == "turn_context":
                        if not isinstance(p.get("turn_id"), str) or any(not isinstance(p.get(k, "unknown"), str) for k in ("model", "effort")):
                            counts["malformed_lines"] += 1
                            context = {}
                            continue
                        context = p
                        active = p.get("turn_id")
                    event = p.get("type") if typ == "event_msg" else None
                    if event == "task_started":
                        active = p.get("turn_id")
                        if context.get("turn_id") != active:
                            context = {}
                    elif event in ("task_complete", "turn_aborted", "task_cancelled") and p.get("turn_id"):
                        active = p["turn_id"]
                    if active is not None and not isinstance(active, str):
                        counts["malformed_lines"] += 1
                        active = None
                    at = timestamp(record.get("timestamp"))
                    identity = (meta.get("id"), active)
                    in_range = at is not None and since <= at <= now
                    if not inherited and in_range and active and meta.get("id") and (typ == "turn_context" or event in ("task_started", "task_complete", "turn_aborted", "task_cancelled", "token_count")):
                        row = turns.setdefault(identity, {"date": at.isoformat(), "thread_id": identity[0], "turn_id": active,
                            "model": "unknown", "reasoning_effort": "unknown", "category": ROLES.get(meta.get("agent_role"), "coordinator" if identity in parents else "unknown"), "status": "unknown",
                            "tokens": {k: 0 for k in FIELDS}, "token_coverage": "unknown", "_segments": set(), "_tokens": {}})
                        if typ == "turn_context":
                            row["category"] = ROLES.get(meta.get("agent_role"), "coordinator" if identity in parents else "unknown")
                        if event == "task_complete":
                            row["status"] = "completed"
                        elif event in ("turn_aborted", "task_cancelled"):
                            row["status"] = "cancelled"
                        elif event == "task_started":
                            row["status"] = "started"
                        model_effort = (context.get("model", "unknown"), context.get("effort", "unknown"))
                        if context and context.get("turn_id") == active:
                            row["_segments"].add(model_effort)
                            row["model"], row["reasoning_effort"] = model_effort if len(row["_segments"]) == 1 else ("mixed", "mixed")
                    if event != "token_count":
                        continue
                    info = p.get("info")
                    total = usage(info.get("total_token_usage")) if isinstance(info, dict) else None
                    current_context = (context.get("model"), context.get("effort"))
                    if total is None:
                        if not inherited and in_range:
                            counts["unknown_token_events"] += 1
                            if identity in turns:
                                turns[identity]["token_coverage"] = "partial"
                        continue
                    if previous is not None and any(total[k] < previous[k] for k in ("input_tokens", "output_tokens", "total_tokens")):
                        reset_epoch += 1
                    signature = (meta.get("id"), active, record.get("timestamp") if isinstance(record.get("timestamp"), str) else None, reset_epoch, tuple(total.values()))
                    duplicate = signature in seen_events
                    seen_events.add(signature)
                    delta = None
                    if previous is not None and all(total[k] >= previous[k] for k in ("input_tokens", "output_tokens", "total_tokens")):
                        if previous_context == current_context:
                            delta = {k: total[k] - previous[k] if total[k] is not None and previous[k] is not None and total[k] >= previous[k] else None for k in FIELDS}
                    else:
                        last = usage(info.get("last_token_usage"))
                        # A first event is complete only when its cumulative total is the last request.
                        if previous is None and last == total:
                            delta = total
                    previous, previous_context = total, current_context
                    if duplicate or inherited or not in_range:
                        continue
                    row = turns.get(identity)
                    if include_events and row:
                        events.append({"id": hashlib.sha256(json.dumps(signature).encode()).hexdigest(),
                            "date": at.isoformat(), "thread_id": identity[0], "turn_id": active,
                            "model": current_context[0] or "unknown", "reasoning_effort": current_context[1] or "unknown",
                            "category": row["category"], "tokens": delta,
                            "speed": context.get("service_tier", "unknown")})
                    if delta is None or row is None or not current_context[0]:
                        counts["unknown_token_events"] += 1
                        if row:
                            row["token_coverage"] = "partial"
                        continue
                    if row["token_coverage"] == "unknown":
                        row["token_coverage"] = "observed"
                    for k in FIELDS:
                        row["tokens"][k] = None if row["tokens"][k] is None or delta[k] is None else row["tokens"][k] + delta[k]
                    segment = row["_tokens"].setdefault(current_context, {k: 0 for k in FIELDS})
                    for k in FIELDS:
                        segment[k] = segment[k] + delta[k] if segment[k] is not None and delta[k] is not None else None
    models = {}
    details = sorted(turns.values(), key=lambda row: (row["date"], row["thread_id"], row["turn_id"]))
    for row in details:
        segments = row.pop("_segments") or {(row["model"], row["reasoning_effort"])}
        segment_tokens = row.pop("_tokens")
        if not segment_tokens:
            row["tokens"] = {k: None for k in FIELDS}
        for model, effort in sorted(segments):
            key = (model, effort, row["category"])
            group = models.setdefault(key, {"model": key[0], "reasoning_effort": key[1], "category": key[2], "execution_turns": 0,
                "tokens": {k: 0 for k in FIELDS}, "turns_with_unknown_or_partial_tokens": 0, "_observed": False})
            group["execution_turns"] += 1
            if row["token_coverage"] != "observed":
                group["turns_with_unknown_or_partial_tokens"] += 1
            for k in FIELDS:
                value = segment_tokens.get((model, effort), {}).get(k, 0)
                group["tokens"][k] = group["tokens"][k] + value if group["tokens"][k] is not None and value is not None else None
            group["_observed"] |= (model, effort) in segment_tokens
    for row in models.values():
        if not row.pop("_observed"):
            row["tokens"] = {k: None for k in FIELDS}
    known = sum(row["tokens"]["total_tokens"] or 0 for row in models.values())
    for row in models.values():
        row["token_share"] = round(row["tokens"]["total_tokens"] / known, 4) if known and row["tokens"]["total_tokens"] is not None else None
    result = {"period": period, "from": since.isoformat(), "to": now.isoformat(), "installation_start": start,
        "execution_turns": len(details), "observed_total_tokens": known, "models": list(models.values()), "details": details[-100:], "details_omitted": max(0, len(details) - 100),
        "coverage": {**{k: counts[k] for k in ("journal_files", "malformed_lines", "unknown_token_events", "excluded_inherited_events", "excluded_system_sessions", "unknown_history_sessions", "unreadable_files")}, "scope": "Local retained sessions and archived_sessions only; all models, including non-router sessions.",
            "notes": ["Categories come from recorded agent roles, not question meaning.", "Execution turns are not user questions or API calls.",
                "Token shares use observed tokens only; missing, reset and model-boundary deltas are excluded.",
                "A turn using multiple models appears in each model row; overall turns are deduplicated.",
                "Cached input is part of input; reasoning output is part of output. These are not costs or account quota."]}}
    if include_events:
        result.update(events=events, turns=details, parent_links=sorted(parents))
    return result
