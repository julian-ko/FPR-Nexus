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
            stamp = f"{st.st_size}:{st.st_mtime_ns}"
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
                         rate_source=RATE_SOURCE, imported_at=now.isoformat())
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
        if before == f"{after.st_size}:{after.st_mtime_ns}" and not report["coverage"]["unreadable_files"]:
            db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?)", (source, key, before, json.dumps(report["coverage"])))
    origin_key = "installation:" + source
    start = installation_start(state)
    if start["at"]:
        db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", (origin_key, json.dumps(start)))
    db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", ("last_collect:" + source, now.isoformat()))
    return source


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
        events = []
        for (body,) in db.execute("SELECT body FROM events WHERE source=?", (source,)):
            e = json.loads(body)
            key = (e["thread_id"], e["turn_id"])
            if key in parents and e["category"] == "unknown":
                e["category"] = "coordinator"
            if scope == "nexus" and e["category"] == "unknown":
                continue
            if lower <= timestamp(e["date"]) < upper:
                events.append(e)
        groups = {}
        totals = {k: 0 for k in FIELDS}
        known_credits = Decimal(0)
        unpriced = 0
        by_turn = defaultdict(lambda: {"estimated_credits": Decimal(0), "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "events": 0, "unpriced_events": 0, "models": set(), "reasoning_efforts": set()})
        for e in events:
            label = e["date"][:10] if group_by == "date" else e["model"] if group_by == "model" else e["category"]
            g = groups.setdefault(label, {"group": label, "tokens": {k: 0 for k in FIELDS}, "estimated_credits": Decimal(0), "unpriced_events": 0, "turns": set(), "missing_fields": set()})
            key = (e["thread_id"], e["turn_id"])
            g["turns"].add(key)
            by_turn[key]["models"].add(e["model"])
            by_turn[key]["reasoning_efforts"].add(e["reasoning_effort"])
            for k in FIELDS:
                value = (e["tokens"] or {}).get(k)
                if value is None:
                    g["missing_fields"].add(k)
                else:
                    g["tokens"][k] += value
                    totals[k] += value
            credits = e["estimated_credits"]
            if credits is None:
                unpriced += 1
                g["unpriced_events"] += 1
                by_turn[key]["unpriced_events"] += 1
            else:
                amount = Decimal(credits)
                known_credits += amount
                g["estimated_credits"] += amount
                by_turn[key]["estimated_credits"] += amount
            for k in ("input_tokens", "cached_input_tokens", "output_tokens"):
                by_turn[key][k] += (e["tokens"] or {}).get(k) or 0
            by_turn[key]["events"] += 1
        selected = set(by_turn)
        for key, row in turns.items():
            nexus = row["category"] != "unknown" or key in parents
            if lower <= timestamp(row["date"]) < upper and (scope == "all" or nexus):
                selected.add(key)
        for g in groups.values():
            g["execution_turns"] = len(g.pop("turns"))
            g["missing_fields"] = sorted(g["missing_fields"])
            g["estimated_credits"] = str(g["estimated_credits"])
        top = []
        for key, values in sorted(by_turn.items(), key=lambda kv: kv[1]["estimated_credits"], reverse=True)[:10]:
            row = turns.get(key, {})
            i, c = values["input_tokens"], values["cached_input_tokens"]
            reasons = ["Multiple observed usage events in one execution turn"] if values["events"] > 1 else []
            if i and c / i >= .5:
                reasons.append("Most input is cached; total tokens overstate its relative credit cost")
            if values["output_tokens"] > i:
                reasons.append("Output tokens dominate; output has a higher unit rate")
            top.append({"thread_id": key[0], "turn_id": key[1], **values, "models": sorted(values["models"]), "reasoning_efforts": sorted(values["reasoning_efforts"]), "estimated_credits": str(values["estimated_credits"]),
                        "category": "coordinator" if key in parents else row.get("category", "unknown"), "evidence": reasons})
        coverage = defaultdict(int)
        for (body,) in db.execute("SELECT coverage FROM files WHERE source=?", (source,)):
            for k, v in json.loads(body).items():
                if type(v) is int:
                    coverage[k] += v
        return {"scope": scope, "from": lower.isoformat(), "to_exclusive": upper.isoformat(), "timezone": "UTC", "installation_start": start,
                "group_by": group_by, "groups": sorted(groups.values(), key=lambda g: g["group"]),
                "execution_turns": len(selected), "observed_tokens": totals, "estimated_credits": str(known_credits),
                "unpriced_events": unpriced, "turns_without_observed_events": len(selected - set(by_turn)),
                "estimate_status": "partial" if unpriced or selected - set(by_turn) or any(turns.get(k, {}).get("token_coverage") != "observed" for k in selected) else "observed_usage_only",
                "standard_speed_assumed_events": sum(e["pricing_reason"] == "standard_assumed" for e in events),
                "stored_rate_versions": sorted({e["rate_version"] for e in events}),
                "turns_with_partial_or_unknown_data": sum(turns.get(k, {}).get("token_coverage") != "observed" for k in selected),
                "high_consumption": top, "coverage": dict(coverage), "history_file": str(directory / "usage.sqlite3"),
                "pricing": {"basis": "Standard credits estimate; company billing unknown; not an invoice or quota", "version": RATE_VERSION,
                            "source": RATE_SOURCE, "historical": "First import uses this rate card even for older usage; stored estimates are not repriced"},
                "notes": ["All means retained local user sessions; cloud, deleted-before-collection and system sessions are not covered.",
                          "Nexus is a subset of all, proven by agent roles and parent links. Unknown is not proven non-Nexus.",
                          "Only observed amounts are summed. Unknown prices, cache splits and nonstandard speeds are not treated as free.",
                          "Token/credit totals may be partial; coverage counters describe scanned files, not only this date range.",
                          "Reasoning is included in output; cached input is included in input. Tool charges and contract discounts are not included.",
                          "Collected statistics survive plugin removal. Collection stops when hooks are removed; no retention expiry is applied.",
                          "Consumption evidence is not a proven cause or a judgement of task quality."]}
    finally:
        db.close()
