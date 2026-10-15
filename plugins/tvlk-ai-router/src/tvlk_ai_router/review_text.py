"""Human-readable review, shared by Terminal and chat commands."""
from decimal import Decimal


def render(report):
    def amount(value):
        return "unknown" if value is None else f"{Decimal(str(value)):,.2f}"

    def table(headers, rows):
        lines.extend(["", "| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"])
        lines.extend("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in row) + " |" for row in rows)

    lines = ["FPR Nexus usage review", "", f"Period: {report['from']} to {report['to_exclusive']} (end excluded). Timezone: UTC.",
             f"Selected scope: {report['scope']}. All means retained local Codex user sessions, including non-Nexus usage.",
             "Nexus is a subset of All. Unattributed may include Nexus work without evidence."]
    table(["Scope", "Execution turns", "Observed tokens", "Estimated credits", "Unpriced events"],
          [[name, row["execution_turns"], f"{row['observed_tokens']['total_tokens']:,}", amount(row["estimated_credits"]), row["unpriced_events"]]
           for name, row in report["scope_comparison"].items()])
    lines.extend(["", "Token and cost split (selected scope; known subtotals)"])
    parts = report["credit_breakdown"]
    t = report["observed_tokens"]
    table(["Part", "Tokens", "Estimated credits"], [
        ["Uncached input", f"{t['uncached_input_tokens']:,}", amount(parts["uncached_input"])],
        ["Cached input", f"{t['cached_input_tokens']:,}", amount(parts["cached_input"])],
        ["Output", f"{t['output_tokens']:,}", amount(parts["output"])],
        ["Reasoning (already in output)", f"{t['reasoning_output_tokens']:,}", "included above"]])
    lines.append(f"Missing credit splits: {report['credit_breakdown_missing_events']} events. Missing token fields: {report['missing_fields']}.")
    sections = {"model": "Models", "task": "Task types", "activity": "Execution roles", "date": "Daily usage (UTC)"}
    for key in (report["group_by"], *(k for k in sections if k != report["group_by"])):
        title = sections[key]
        lines.extend(["", title])
        table([title, "Turns", "Tokens", "Credits", "Known credit share", "Avg credits/turn", "Unpriced"],
              [[g["group"], g["execution_turns"], f"{g['observed_tokens']['total_tokens']:,}", amount(g["estimated_credits"]),
                f"{g['known_credit_share']:.1%}" if g["known_credit_share"] is not None else "unknown",
                amount(g["average_estimated_credits_per_turn"]), g["unpriced_events"]] for g in report["by_" + key]])
    lines.extend(["", "Largest observed contributors (up to 5; no optimization recommendations)"])
    for row in report["high_consumption"]:
        lines.append(f"- {row['date']}: {', '.join(row['models'])}; task={row['category']}; activity={row['activity']}; "
                     f"{amount(row['estimated_credits'])} credits; {row['usage_events']} usage observations; "
                     f"{row['unpriced_events']} unpriced. Thread {row['thread_id']}, turn {row['turn_id']}.")
        if row["evidence"]:
            lines.append("  Evidence: " + "; ".join(row["evidence"]) + ".")
    decisions = report["routing_records"]
    lines.extend(["", f"Routing records: {len(decisions)} attributed or linked turns; showing up to 5 recent records. --json includes all records."])
    for row in sorted(decisions, key=lambda r: r["date"], reverse=True)[:5]:
        choices = "; ".join(f"{d['task_type']}/{d['mode']}, reason={d['reason']}, selected={d['selected_model']}/{d['selected_effort']}" for d in row["route_decisions"]) or "selection reason unknown"
        lines.append(f"- {row['thread_id']}/{row['turn_id']}: {choices}; actual models={','.join(row['observed_models']) or 'unknown'}; "
                     f"actual efforts={','.join(row['observed_efforts']) or 'unknown'}; parent={row['parent_thread_id'] or 'unknown'}/{row['parent_turn_id'] or 'unknown'}; evidence={row['attribution_basis']}.")
    lines.extend(["", "Data quality",
                  f"Estimate: {report['estimate_status']}; partial/unknown turns: {report['turns_with_partial_or_unknown_data']}; "
                  f"turns without events: {report['turns_without_observed_events']}; unpriced events: {report['unpriced_events']}.",
                  f"Unknown task turns: {report['unknown_task_turns']}; unknown attribution turns: {report['unknown_attribution_turns']}.",
                  f"Standard speed assumed: {report['standard_speed_assumed_events']} events. Unpriced reasons: {report['unpriced_reasons']}.",
                  f"Whole-file scan coverage (not just the date range): {report['coverage']}.", "", "Rates (credits per 1 million tokens)"])
    table(["Model", "Rate version", "Uncached input", "Cached input", "Output"],
          [[r["model"], r["version"], *[r["credits_per_million"][k] for k in ("uncached_input", "cached_input", "output")]] for r in report["rates_used"]])
    lines.extend([f"Source: {report['pricing']['source']}", report["pricing"]["basis"], report["pricing"]["historical"], ""])
    lines.extend(report["notes"])
    return "\n".join(lines)
