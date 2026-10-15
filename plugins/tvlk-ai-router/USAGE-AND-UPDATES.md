# FPR Nexus 1.2.0

## What

- Keep local usage statistics after the plugin is removed.
- View all recorded local Codex usage or the Nexus subset.
- One report includes scope comparison, token/cost splits, UTC dates, models, task types and execution roles.
- Record future routing choices and show actual parent/child usage separately.
- Check the latest version and required upgrade date.
- No usage data is sent to a server.

## Why

Token share is not cost share. Cached input and model prices matter. Nexus uses the public Standard credits rate card verified on 15 October 2026 as a default estimate. Company billing is unknown. Estimates are not an invoice, cash spending or subscription quota.

Statistics are saved in `~/.local/share/fpr-nexus-history/usage.sqlite3`, outside the plugin cache and configuration backups. There is no expiry. Keep this directory when removing the plugin or moving to a new computer. Collection stops when the plugin is removed; previously saved statistics remain.

Nexus membership uses a recorded Nexus choice, a known custom agent role or a parent-turn link. All includes retained local user sessions, not every device, cloud task or system agent. Unattributed may contain Nexus work without enough evidence. Unknown historical task types stay unknown; they are not guessed from model names or message text. Deleted-before-collection logs cannot be recovered. No prompt, code, reply or tool output is stored in the ledger.

## How

Enter in Codex chat:

```text
tvlk-ai-router review since-install
tvlk-ai-router review 30d --scope nexus --group-by task
tvlk-ai-router review 30d --group-by model
tvlk-ai-router review --from 2026-10-01 --to 2026-10-15 --group-by date
tvlk-ai-router update check
```

Each review imports changed local logs. Trusted hooks also schedule collection at session start, prompts, turn completion and session end. Collection is best-effort: use `review all` before uninstall to capture final usage. Back up the history directory if protection from device loss is needed.

The report has six short parts:

1. **Scope:** All local usage, Nexus usage and unattributed usage. Nexus is part of All; do not add them together.
2. **Tokens and credits:** Uncached input, cached input and output. Reasoning is a part of output, not an extra charge.
3. **Breakdowns:** Models, task types, execution roles and UTC dates, with turns, credits, shares and average credits per turn. A turn can appear on more than one date or model row.
4. **Largest contributors:** Up to five turns with dates, models, usage observations and measured evidence. Observations are not a reliable API-call count.
5. **Routing records:** Selected task, reason code and model/effort, alongside observed models and parent/child IDs. Use `--json` for every record; the normal report shows five recent records.
6. **Data quality:** Missing token fields, unpriced events, unknown tasks, rate versions and assumed Standard speed. Zeros are known subtotals when data is missing.

For new work, trusted routing hooks ask the main assistant to save one small local record before execution. Fixed types are coding, writing, product, analysis and unknown. Fixed reason codes describe code changes, text edits, product design, complex analysis, user choice, simple work, mixed work or management. No free-text reason is saved. Identical retries are deduplicated; changed choices remain visible as mixed intent. Selected settings are intent, not proof that execution succeeded or used that model.

Journal roles identify executors and parent/child relationships. The report separates coordinator, executor, direct and unknown activity. Coordinator usage includes reading context, tools and summaries; it is not a measured classification-only cost. If hooks are disabled, the assistant skips recording, or the journal has no valid active turn, attribution can remain unknown. Recording failures do not stop the user's work. Existing records remain after removal, including records whose source logs are later deleted.

This release implements complete reporting and task records only. It does not produce automatic optimization recommendations or upload usage.

Read estimated credits alongside missing/unpriced events and partial-turn counts. Missing cache splits, unknown model prices and explicit nonstandard speed modes are unpriced. If speed is not recorded, Standard is assumed and identified. Historical imports use the default rate card; saved estimates keep their original price version. High-consumption evidence explains measured input/output/cache patterns, not task quality or proven waste.

For an update, refresh FPR Nexus in Codex first. Start a new chat and enter:

```text
tvlk-ai-router update prepare
```

Leave the setup window open, quit clients when asked, and let setup continue. Backup checks, client-exit checks and failure recovery remain in place. A window waiting for client exit is not a completed update.

Version policy comes from `releases/policy.json` in the public FPR-Nexus GitHub repository. Only version metadata is fetched; usage is not uploaded. Existing 1.0.8 installations need one normal upgrade first. A required upgrade limits Nexus guidance and configuration activation. Direct Codex use, review, disable and recovery remain available. This is not company-wide enforcement.

Official references: [Pricing](https://learn.chatgpt.com/docs/pricing), [Hooks](https://learn.chatgpt.com/docs/hooks).
