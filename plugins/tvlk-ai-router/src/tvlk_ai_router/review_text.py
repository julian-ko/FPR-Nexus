"""Tables from the same snapshot as the portable JSON, without local analysis."""
import json
from decimal import Decimal


def render(report):
    def amount(value):
        return "unknown" if value is None else f"{Decimal(str(value)):,.4f}"

    def table(headers, rows):
        lines.extend(["", "| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"])
        lines.extend("| " + " | ".join(("unknown" if v is None else str(v)).replace("|", "\\|").replace("\n", " ") for v in row) + " |" for row in rows)

    period, summary = report["period"], report["summary"]
    lines = ["# FPR Nexus usage review", "", f"Period: {period['from_inclusive']} to {period['to_exclusive']} (end excluded). Timezone: UTC.",
             f"Selected scope: {report['selected_scope']}. Nexus is a subset of All; unattributed is not proven non-Nexus.",
             "", "## 1. Summary"]
    table(["Scope", "Turns", "Usage events", "Observed tokens", "Estimated credits", "Unpriced events", "Status"],
          [[name, r["execution_turns"], r["usage_events"], r["observed_tokens"]["total_tokens"], amount(r["estimated_credits"]), r["unpriced_events"], r["estimate_status"]]
           for name, r in report["scope_comparison"].items()])
    table(["Part (selected scope)", "Tokens", "Estimated credits"],
          [[label, summary["observed_tokens"][token], amount(summary["credit_breakdown"][part]) if part else "included in output"]
           for label, token, part in (("Uncached input", "uncached_input_tokens", "uncached_input"),
                                     ("Cached input", "cached_input_tokens", "cached_input"), ("Output", "output_tokens", "output"),
                                     ("Reasoning (already in output)", "reasoning_output_tokens", None))])
    lines.extend(["", "## 2. Model and reasoning effort"])
    table(["Model", "Reasoning effort", "Turns", "Uncached input", "Cached input", "Output", "Estimated credits", "Unpriced events"],
          [[r["model"], r["reasoning_effort"], r["execution_turns"], *[r["observed_tokens"][k] for k in ("uncached_input_tokens", "cached_input_tokens", "output_tokens")],
            amount(r["estimated_credits"]), r["unpriced_events"]] for r in report["by_model_reasoning_effort"]])
    lines.extend(["", "## 3. Date, model, reasoning effort and task"])
    table(["Date (UTC)", "Model", "Reasoning effort", "Task type", "Turns", "Observed tokens", "Estimated credits", "Unpriced events"],
          [[r["date_utc"], r["model"], r["reasoning_effort"], r["task_type"], r["execution_turns"], r["observed_tokens"]["total_tokens"],
            amount(r["estimated_credits"]), r["unpriced_events"]] for r in report["by_date_model_reasoning_task"]])
    lines.extend(["", "## 4. Usage records (first 5)", "", f"JSON contains all {len(report['records'])} records. Values below are observations, not API-call counts."])
    table(["Event ID", "Time (UTC)", "Model", "Reasoning effort", "Task type", "Activity", "Input", "Cached input", "Output", "Reasoning output", "Total", "Estimated credits"],
          [[r["event_id"], r["timestamp_utc"], r["model"], r["reasoning_effort"], r["task_type"], r["activity"],
            *[r["token_usage"][k] for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")],
            amount(r["estimated_credits"])] for r in report["records"][:5]])
    lines.extend(["", "## 5. Missing data and assumptions"])
    table(["Field", "Value"], [[name, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value]
          for name, value in {**{k: summary[k] for k in ("estimate_status", "missing_fields", "unpriced_events", "unpriced_reasons",
            "credit_breakdown_missing_events", "turns_without_observed_events", "turns_with_partial_or_unknown_data", "standard_speed_assumed_events", "stored_rate_versions")},
            **report["coverage"]["period"], "whole_file_scan": report["coverage"]["whole_file_scan"]}.items()])
    table(["Model", "Rate version", "Uncached input / 1M", "Cached input / 1M", "Output / 1M"],
          [[r["model"], r["version"], *[r["credits_per_million"][k] for k in ("uncached_input", "cached_input", "output")]] for r in report["rate_cards"]])
    lines.extend(["", report["pricing"]["basis"], report["pricing"]["historical"], f"Rate source: {report['pricing']['source']}", ""])
    lines.extend(report["notes"])
    lines.extend(["", "No local analysis or upload. Merge overlapping JSON exports by event_id; do not add snapshot totals.",
                  "Credits are decimal strings in JSON. Table values are rounded; zero totals may be partial. Unknown does not mean free."])
    for kind, path in report.get("exports", {}).items():
        lines.append(f"\nSaved {kind}: {path}")
    return "\n".join(lines)
