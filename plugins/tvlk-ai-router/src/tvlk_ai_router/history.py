"""Durable local usage ledger. Never retain prompts, paths from tools, or replies."""
import hashlib
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .config import RouterError
from .usage import FIELDS, installation_start, review, timestamp

RATE_VERSION = "codex-standard-credits-2026-10-15"
RATE_SOURCE = "https://learn.chatgpt.com/docs/pricing"
RATES = {"gpt-6-astra": (250, 25, 1250), "gpt-6.1-sol": (50, 2.5, 250),
         "gpt-6-sol": (50, 5, 250), "gpt-6-luna": (2.5, .25, 12.5),
         "gpt-5.6-sol": (100, 10, 500), "gpt-5.6-terra": (50, 5, 300),
         "gpt-5.6-luna": (5, .5, 30)}
RATE_CARDS = {RATE_VERSION: dict(RATES)}
PARSER_VERSION = "2"


def estimate(event):
    tokens = event.get("tokens")
    rate = RATES.get(event["model"])
    if not tokens or not rate:
        return None, "missing_tokens_or_model_price"
    i, c, o = (tokens.get(k) for k in ("input_tokens", "cached_input_tokens", "output_tokens"))
    if any(type(n) is not int or n < 0 for n in (i, c, o)) or c > i:
        return None, "missing_or_invalid_cache_split"
    if event.get("speed") not in (None, "unknown", "default", "standard"):
        return None, "nonstandard_speed_not_priced"
    value = sum(Decimal(n) * Decimal(str(r)) for n, r in zip((i-c, c, o), rate)) / 1000000
    return str(value), "standard_assumed" if event.get("speed") in (None, "unknown") else "standard_recorded"


def connect(directory):
    for p in (directory, *directory.parents):
        if p.is_symlink():
            raise RouterError("History paths must not contain symbolic links", 4)
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    path = directory / "usage.sqlite3"
    for p in (path, directory / "usage.sqlite3-journal", directory / "usage.sqlite3-wal", directory / "usage.sqlite3-shm"):
        if p.is_symlink():
            raise RouterError("History database must not be a symbolic link", 4)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    path.chmod(0o600)
    db = sqlite3.connect(path, timeout=30)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS events (source TEXT, id TEXT, body TEXT, PRIMARY KEY(source,id));
        CREATE TABLE IF NOT EXISTS turns (source TEXT, thread TEXT, turn TEXT, body TEXT, PRIMARY KEY(source,thread,turn));
        CREATE TABLE IF NOT EXISTS parents (source TEXT, thread TEXT, turn TEXT, PRIMARY KEY(source,thread,turn));
        CREATE TABLE IF NOT EXISTS files (source TEXT, path TEXT, stamp TEXT, coverage TEXT, PRIMARY KEY(source,path));
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS routes (source TEXT, thread TEXT, turn TEXT, id TEXT, body TEXT, PRIMARY KEY(source,thread,turn,id));
    """)
    return db


def collect(db, home, state, now):
    source = hashlib.sha256(str(home).encode()).hexdigest()
    changes, stamps = [], {}
    for name in ("sessions", "archived_sessions"):
        directory = home / name
        if directory.is_symlink():
            continue
        for path in sorted(directory.rglob("*.jsonl")):
            if path.is_symlink() or any(p.is_symlink() for p in path.parents):
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            key = hashlib.sha256(str(path).encode()).hexdigest()
            stamp = f"{PARSER_VERSION}:{st.st_size}:{st.st_mtime_ns}"
            old = db.execute("SELECT stamp FROM files WHERE source=? AND path=?", (source, key)).fetchone()
            if not old or old[0] != stamp:
                changes.append(path)
                stamps[path] = (key, stamp)
    # Parse changed files only. Cross-file coordinator links persist separately.
    for path in changes:
        report = review(home, state, "all", now, paths=[path], include_events=True)
        for event in report["events"]:
            credits, reason = estimate(event)
            event.update(estimated_credits=credits, pricing_reason=reason, rate_version=RATE_VERSION,
                         rate_source=RATE_SOURCE, imported_at=now.isoformat(), unit_rates=RATES.get(event["model"]))
            db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?)", (source, event["id"], json.dumps(event)))
        for row in report["turns"]:
            key = (source, row["thread_id"], row["turn_id"])
            old = db.execute("SELECT body FROM turns WHERE source=? AND thread=? AND turn=?", key).fetchone()
            if old:
                previous = json.loads(old[0])
                if previous["date"] < row["date"]:
                    row["date"] = previous["date"]
                if previous["status"] in ("completed", "cancelled"):
                    row["status"] = previous["status"]
                if previous["category"] != "unknown":
                    row["category"] = previous["category"]
            # Token totals are derived from immutable events, not truncated turn snapshots.
            row.pop("tokens", None)
            db.execute("INSERT OR REPLACE INTO turns VALUES(?,?,?,?)", (*key, json.dumps(row)))
        for thread, turn in report["parent_links"]:
            db.execute("INSERT OR IGNORE INTO parents VALUES(?,?,?)", (source, thread, turn))
        key, before = stamps[path]
        after = path.stat()
        if before == f"{PARSER_VERSION}:{after.st_size}:{after.st_mtime_ns}" and not report["coverage"]["unreadable_files"]:
            db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?)", (source, key, before, json.dumps(report["coverage"])))
    origin_key = "installation:" + source
    start = installation_start(state)
    if start["at"]:
        db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", (origin_key, json.dumps(start)))
    db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", ("last_collect:" + source, now.isoformat()))
    return source


def credit_parts(event):
    """Recover old price splits only when they exactly match the saved estimate."""
    rates = event.get("unit_rates") or RATE_CARDS.get(event["rate_version"], {}).get(event["model"])
    tokens = event.get("tokens") or {}
    values = [tokens.get(k) for k in ("input_tokens", "cached_input_tokens", "output_tokens")]
    if event["estimated_credits"] is None or not rates or any(type(n) is not int or n < 0 for n in values) or values[1] > values[0]:
        return None, None
    i, c, o = values
    parts = {k: Decimal(n) * Decimal(str(r)) / 1000000 for k, n, r in zip(
        ("uncached_input", "cached_input", "output"), (i-c, c, o), rates)}
    if sum(parts.values()) != Decimal(event["estimated_credits"]):
        return None, None
    return parts, list(rates)


def summarize(events, selected, turns):
    totals = {k: 0 for k in (*FIELDS, "uncached_input_tokens")}
    missing = defaultdict(int)
    credits, parts = Decimal(0), {k: Decimal(0) for k in ("uncached_input", "cached_input", "output")}
    unpriced, unsplit, assumed = 0, 0, 0
    reasons, rates, observed, partial = defaultdict(int), {}, set(), set()
    for e in events:
        key = (e["thread_id"], e["turn_id"])
        observed.add(key)
        tokens = e.get("tokens") or {}
        i, c = tokens.get("input_tokens"), tokens.get("cached_input_tokens")
        values = {**tokens, "uncached_input_tokens": i-c if type(i) is int and type(c) is int and 0 <= c <= i else None}
        for name in totals:
            value = values.get(name)
            if value is None:
                missing[name] += 1
                partial.add(key)
            else:
                totals[name] += value
        if e["estimated_credits"] is None:
            unpriced += 1
            partial.add(key)
            reasons[e["pricing_reason"]] += 1
        else:
            credits += Decimal(e["estimated_credits"])
        split, unit = credit_parts(e)
        if split is None:
            unsplit += 1
        else:
            for name, value in split.items():
                parts[name] += value
            rates[(e["model"], e["rate_version"], tuple(unit))] = {
                "model": e["model"], "version": e["rate_version"], "source": e.get("rate_source"),
                "credits_per_million": dict(zip(("uncached_input", "cached_input", "output"), unit))}
        assumed += e["pricing_reason"] == "standard_assumed"
    absent = selected - observed
    partial |= {k for k in selected if turns.get(k, {}).get("token_coverage") != "observed"}
    return {"execution_turns": len(selected), "usage_events": len(events), "observed_tokens": totals,
            "estimated_credits": str(credits), "credit_breakdown": {k: str(v) for k, v in parts.items()},
            "credit_breakdown_missing_events": unsplit, "unpriced_events": unpriced,
            "unpriced_reasons": dict(reasons), "missing_fields": dict(missing),
            "turns_without_observed_events": len(absent), "turns_with_partial_or_unknown_data": len(partial),
            "unknown_task_turns": sum(turns.get(k, {}).get("task_type", "unknown") == "unknown" for k in selected),
            "unknown_attribution_turns": sum(turns.get(k, {}).get("activity", "unknown") == "unknown" for k in selected),
            "standard_speed_assumed_events": assumed, "stored_rate_versions": sorted({e["rate_version"] for e in events}),
            "rates_used": list(rates.values()), "estimate_status": "partial" if unpriced or partial or absent else "observed_usage_only",
            "average_estimated_credits_per_turn": str(credits / len(selected)) if selected else None}


def grouped(events, selected, turns, dimension):
    buckets, keys = defaultdict(list), defaultdict(set)
    def label(row):
        return row["date"][:10] if dimension == "date" else row.get({"model": "model", "task": "task_type", "activity": "activity"}[dimension], "unknown")
    observed = set()
    for event in events:
        name, key = label(event), (event["thread_id"], event["turn_id"])
        buckets[name].append(event)
        keys[name].add(key)
        observed.add(key)
    # A turn without usage still belongs in the denominator and missing-data view.
    for key in selected - observed:
        keys[label(turns[key])].add(key)
    total = sum((Decimal(e["estimated_credits"]) for e in events if e["estimated_credits"] is not None), Decimal(0))
    rows = []
    for name in sorted(keys):
        summary = summarize(buckets[name], keys[name], turns)
        rows.append({"group": name, **summary, "tokens": summary["observed_tokens"],
                     "known_credit_share": float(Decimal(summary["estimated_credits"]) / total) if total else None})
    return rows


def report(manager, period="7d", scope="all", group_by="model", since=None, until=None, now=None):
    now = now or datetime.now(timezone.utc)
    if scope not in ("all", "nexus") or group_by not in ("date", "model", "task"):
        raise RouterError("Invalid review scope or grouping", 4)
    directory = manager.data.parent / "fpr-nexus-history"
    db = connect(directory)
    try:
        with db:
            source = collect(db, manager.home, manager.state, now)
        origin = db.execute("SELECT value FROM meta WHERE key=?", ("installation:" + source,)).fetchone()
        start = json.loads(origin[0]) if origin else installation_start(manager.state)
        if since:
            lower = timestamp(since + "T00:00:00Z")
        elif period == "since-install":
            lower = timestamp(start["at"])
        elif period == "all":
            lower = datetime(1970, 1, 1, tzinfo=timezone.utc)
        else:
            lower = now - timedelta(days=int(period[:-1]))
        upper = timestamp(until + "T00:00:00Z") + timedelta(days=1) if until and timestamp(until + "T00:00:00Z") else (None if until else now)
        if lower is None or upper is None or lower > upper:
            raise RouterError("Use valid YYYY-MM-DD dates; installation date may be unknown", 4)
        parents = {(t, u) for t, u in db.execute("SELECT thread,turn FROM parents WHERE source=?", (source,))}
        turns = {(t, u): json.loads(b) for t, u, b in db.execute("SELECT thread,turn,body FROM turns WHERE source=?", (source,))}
        routes = defaultdict(list)
        for thread, turn, body in db.execute("SELECT thread,turn,body FROM routes WHERE source=? ORDER BY rowid", (source,)):
            routes[(thread, turn)].append(json.loads(body))
        from .routing import attribution
        for key, row in turns.items():
            row.update(attribution(key, row, parents, routes))
        events = []
        for (body,) in db.execute("SELECT body FROM events WHERE source=?", (source,)):
            e = json.loads(body)
            key = (e["thread_id"], e["turn_id"])
            e.update(attribution(key, turns.get(key, e), parents, routes))
            if lower <= timestamp(e["date"]) < upper:
                events.append(e)
        selected = {(e["thread_id"], e["turn_id"]) for e in events}
        for key, row in turns.items():
            if lower <= timestamp(row["date"]) < upper:
                selected.add(key)
        nexus_keys = {k for k in selected if turns.get(k, {}).get("nexus")}
        nexus_events = [e for e in events if e["nexus"]]
        comparison = {"all": summarize(events, selected, turns),
                      "nexus": summarize(nexus_events, nexus_keys, turns),
                      "unattributed": summarize([e for e in events if not e["nexus"]], selected - nexus_keys, turns)}
        if scope == "nexus":
            events, selected = nexus_events, nexus_keys
        summary = summarize(events, selected, turns)
        views = {name: grouped(events, selected, turns, name) for name in ("model", "task", "date", "activity")}
        by_turn = defaultdict(list)
        for e in events:
            by_turn[(e["thread_id"], e["turn_id"])].append(e)
        top = []
        ordered = sorted(by_turn, key=lambda k: sum((Decimal(e["estimated_credits"]) for e in by_turn[k] if e["estimated_credits"] is not None), Decimal(0)), reverse=True)
        for key in ordered[:5]:
            row = turns.get(key, {})
            values = summarize(by_turn[key], {key}, turns)
            i, c = (values["observed_tokens"][k] for k in ("input_tokens", "cached_input_tokens"))
            reasons = ["Multiple observed usage events in one execution turn"] if values["usage_events"] > 1 else []
            if i and c / i >= .5:
                reasons.append("Most input is cached; total tokens overstate its relative credit cost")
            if values["observed_tokens"]["output_tokens"] > i:
                reasons.append("Output tokens dominate; output has a higher unit rate")
            top.append({"thread_id": key[0], "turn_id": key[1], "date": row.get("date"), **values,
                        "models": sorted({e["model"] for e in by_turn[key]}), "reasoning_efforts": sorted({e["reasoning_effort"] for e in by_turn[key]}),
                        "category": row.get("task_type", "unknown"), "activity": row.get("activity", "unknown"), "evidence": reasons,
                        "parent_thread_id": row.get("parent_thread_id"), "parent_turn_id": row.get("parent_turn_id"),
                        "route_decisions": row.get("route_decisions", []), "attribution_basis": row.get("attribution_basis", "unknown")})
        coverage = defaultdict(int)
        for (body,) in db.execute("SELECT coverage FROM files WHERE source=?", (source,)):
            for k, v in json.loads(body).items():
                if type(v) is int:
                    coverage[k] += v
        return {"scope": scope, "from": lower.isoformat(), "to_exclusive": upper.isoformat(), "timezone": "UTC", "installation_start": start,
                "group_by": group_by, "groups": views[group_by], **summary,
                "scope_comparison": comparison, "by_model": views["model"], "by_task": views["task"], "by_date": views["date"], "by_activity": views["activity"],
                "routing_records": [{"thread_id": k[0], "turn_id": k[1], "date": turns[k]["date"],
                    **{name: turns[k].get(name) for name in ("task_type", "activity", "attribution_basis", "parent_thread_id", "parent_turn_id", "route_decisions", "selection_scope")},
                    "observed_models": sorted({e["model"] for e in by_turn[k]}),
                    "observed_efforts": sorted({e["reasoning_effort"] for e in by_turn[k]})}
                    for k in sorted(selected) if k in turns and (turns[k]["nexus"] or turns[k].get("parent_thread_id"))],
                "high_consumption": top, "coverage": dict(coverage), "history_file": str(directory / "usage.sqlite3"),
                "pricing": {"basis": "Standard credits estimate; company billing unknown; not an invoice or quota", "version": RATE_VERSION,
                            "source": RATE_SOURCE, "historical": "First import uses this rate card even for older usage; stored estimates are not repriced"},
                "notes": ["All means retained local user sessions; cloud, deleted-before-collection and system sessions are not covered.",
                          "Nexus is a subset of all, attributed by recorded route choices, agent roles or parent links. Unattributed is not proven non-Nexus.",
                          "Task type records selected intent; actual execution comes from journal models and roles. Selection alone does not prove delegation succeeded.",
                          "Coordinator usage includes reading, tools and summaries; it is not a measured classification-only cost. Mixed means multiple recorded choices.",
                          "All, Nexus and unattributed are comparisons, not additive totals. Unknown historic tasks are not guessed from text or model names.",
                          "Dates are UTC usage-event dates. A turn spanning dates or models appears in several groups; group turn counts are not additive.",
                          "Usage events are observations, not a reliable API-call count. Average credits use known credits and all selected turns, and can be partial.",
                          "Only observed amounts are summed. Unknown prices, cache splits and nonstandard speeds are not treated as free.",
                          "Token/credit totals may be partial; coverage counters describe scanned files, not only this date range.",
                          "Reasoning is included in output; cached input is included in input. Tool charges and contract discounts are not included.",
                          "Collected statistics survive plugin removal. Collection stops when hooks are removed; no retention expiry is applied.",
                          "Consumption evidence is not a proven cause or a judgement of task quality."]}
    finally:
        db.close()
