# FPR Nexus 1.1.0

## What

- Keep local usage statistics after the plugin is removed.
- View all recorded local Codex usage or the Nexus subset.
- Group by UTC date, model or task role. Show estimated credits and missing data.
- Check the latest version and required upgrade date.
- No usage data is sent to a server.

## Why

Token share is not cost share. Cached input and model prices matter. Nexus uses the public Standard credits rate card verified on 15 October 2026 as a default estimate. Company billing is unknown. Estimates are not an invoice, cash spending or subscription quota.

Statistics are saved in `~/.local/share/fpr-nexus-history/usage.sqlite3`, outside the plugin cache and configuration backups. There is no expiry. Keep this directory when removing the plugin or moving to a new computer. Collection stops when the plugin is removed; previously saved statistics remain.

Nexus membership requires a known custom agent role or a parent-turn link. Unknown task types stay unknown. All includes retained local user sessions, not every device, cloud task or system agent. Deleted-before-collection logs cannot be recovered. No prompt, code, reply or tool output is stored in the ledger.

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

Read estimated credits alongside missing/unpriced events and partial-turn counts. Missing cache splits, unknown model prices and explicit nonstandard speed modes are unpriced. If speed is not recorded, Standard is assumed and identified. Historical imports use the default rate card; saved estimates keep their original price version. High-consumption evidence explains measured input/output/cache patterns, not task quality or proven waste.

For an update, refresh FPR Nexus in Codex first. Start a new chat and enter:

```text
tvlk-ai-router update prepare
```

Leave the setup window open, quit clients when asked, and let setup continue. Backup checks, client-exit checks and failure recovery remain in place. A window waiting for client exit is not a completed update.

Version policy comes from `releases/policy.json` in the public FPR-Nexus GitHub repository. Only version metadata is fetched; usage is not uploaded. Existing 1.0.8 installations need one normal upgrade first. A required upgrade limits Nexus guidance and configuration activation. Direct Codex use, review, disable and recovery remain available. This is not company-wide enforcement.

Official references: [Pricing](https://learn.chatgpt.com/docs/pricing), [Hooks](https://learn.chatgpt.com/docs/hooks).
