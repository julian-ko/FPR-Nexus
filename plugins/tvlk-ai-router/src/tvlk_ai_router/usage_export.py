"""Portable usage snapshots and private, paired JSON/Markdown exports."""
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

from . import __version__
from .config import RouterError


SUMMARY_FIELDS = ("execution_turns", "usage_events", "observed_tokens", "estimated_credits", "credit_breakdown",
                  "credit_breakdown_missing_events", "unpriced_events", "unpriced_reasons", "missing_fields",
                  "turns_without_observed_events", "turns_with_partial_or_unknown_data", "standard_speed_assumed_events",
                  "stored_rate_versions", "estimate_status")


def dataset(report):
    def summary(row):
        return {k: row[k] for k in SUMMARY_FIELDS}
    return {
        "schema_version": "1.0.0", "dataset": "fpr_nexus_usage", "plugin_version": __version__,
        "installation_start": report["installation_start"],
        "period": {"from_inclusive": report["from"], "to_exclusive": report["to_exclusive"], "timezone": "UTC"},
        "scope": "retained_local_codex_user_sessions", "selected_scope": report["scope"],
        "measurement": {"cost_unit": "credits", "billing_basis": "stored_standard_rate_estimate", "actual_company_bill": False,
            "credit_values": "decimal_strings", "unknown_values": "null_or_unknown", "totals": "observed_subtotals",
            "cached_input_is_subset_of_input": True, "reasoning_output_is_subset_of_output": True,
            "usage_events_are_api_calls": False, "group_turn_counts_are_additive": False,
            "task_attribution": "recorded_choices_roles_and_parent_links", "analysis_included": False},
        "summary": summary(report), "scope_comparison": {k: summary(v) for k, v in report["scope_comparison"].items()},
        "by_model_reasoning_effort": [{**{k: r[k] for k in ("model", "reasoning_effort")}, **summary(r)} for r in report["by_model_reasoning_effort"]],
        "by_date_model_reasoning_task": [{**{k: r[k] for k in ("date_utc", "model", "reasoning_effort", "task_type")}, **summary(r)} for r in report["by_date_model_reasoning_task"]],
        "coverage": {"period": {k: report[k] for k in ("unknown_task_turns", "unknown_attribution_turns")}, "whole_file_scan": report["coverage"]},
        "rate_cards": report["rates_used"], "routing_records": report["routing_records"], "records": report["records"],
        "notes": report["notes"], "pricing": report["pricing"]}


def save(report, directory):
    from .review_text import render
    for path in (directory, *directory.parents):
        if path.is_symlink():
            raise RouterError("Usage export paths must not contain symbolic links", 4)
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    now = datetime.now(timezone.utc)
    report["snapshot_id"] = uuid4().hex
    report["generated_at"] = now.isoformat()
    target = directory / (now.strftime("%Y%m%dT%H%M%S.%fZ-") + report["snapshot_id"])
    stage = None
    try:
        stage = tempfile.mkdtemp(prefix=".pending-", dir=directory)
        for name, content in (("usage.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
                              ("usage.md", render(report) + "\n")):
            fd = os.open(os.path.join(stage, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        if target.exists():
            raise RouterError("Usage export already exists; previous files were preserved", 4)
        os.rename(stage, target)
        stage = None
    finally:
        if stage is not None:
            shutil.rmtree(stage)
    return {"json": str(target / "usage.json"), "table": str(target / "usage.md")}
