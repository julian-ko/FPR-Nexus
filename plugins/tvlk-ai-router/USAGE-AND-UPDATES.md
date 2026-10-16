# FPR Nexus 1.4.0

## What

- Route work with the existing model and reasoning settings.
- Keep usage by date, model, reasoning effort and task type.
- Every review saves one JSON file and one Markdown table file from the same snapshot.
- Keep all local Codex usage separate from the proven Nexus subset.
- Preserve statistics and exports after plugin removal. No usage upload.

## Why

Token share is not cost share. Cached input and model prices matter. Credits use the stored public Standard rate estimate, not the company's actual bill, cash spending or subscription quota. The default rate card was verified on 15 October 2026; saved estimates keep their original version.

Unknown data stays unknown. Task types come from recorded route choices, agent roles or parent links. They are not guessed from model names or private messages. Selected settings describe intent; journal records show actual models and reasoning effort.

## How

Enter in Codex chat:

```text
tvlk-ai-router review since-install
tvlk-ai-router review 30d --scope nexus
tvlk-ai-router review --from 2026-10-01 --to 2026-10-15
tvlk-ai-router review all --json
```

Each review collects changed local journals, then saves:

```text
~/.local/share/fpr-nexus-history/
  usage.sqlite3
  exports/
    <UTC timestamp>-<snapshot ID>/
      usage.json
      usage.md
```

The output includes both file paths. New exports do not replace old exports. A failed write does not publish half of a pair. Directories are private (0700); files are private (0600). No prompt, code, reply or tool output is exported.

The table has five sections:

1. **Summary:** UTC time range, All/Nexus/unattributed usage, turns, usage events, tokens and credits.
2. **Model and reasoning effort:** Turns, uncached input, cached input, output and estimated credits.
3. **Date, model, effort and task:** Daily rows with turns, tokens and credits.
4. **First five records:** The JSON contains every usage record and all routing records.
5. **Missing data:** Unknown fields, unpriced events, partial coverage, speed assumptions and rate versions.

JSON schema `1.0.0` contains `period`, `selected_scope`, `measurement`, `summary`, `scope_comparison`, `by_model_reasoning_effort`, `by_date_model_reasoning_task`, `coverage`, `rate_cards`, `routing_records` and `records`. Each snapshot has a unique ID, UTC creation time and plugin version. Credit amounts are decimal strings; missing amounts are null. Table credit values are rounded to four decimal places. The command's JSON response adds local export paths; the saved portable JSON does not include those paths.

For later upload, merge overlapping snapshots by `event_id`. Do not add snapshot totals. Raw usage events are not a reliable API-call count. Nexus is part of All. Turns spanning models, reasoning settings or dates can appear in several groups. Cache is part of input; reasoning is part of output. All amounts are observed subtotals; zero does not mean free when fields are missing.

`--json` now uses the portable schema above instead of the 1.2.0 flat report. Existing period, scope and date arguments still work. `--group-by` remains accepted; all five table sections are always shown in the fixed order. There is no local analysis, largest-contributor explanation or automatic recommendation.

Trusted hooks collect usage in the background and ask the assistant to record routing choices. These records remain local. Collection is best-effort: missing hooks, deleted journals or skipped route records can leave gaps. All means retained local user sessions, not every device or cloud task. Run `review all` before removal, and keep the history directory. There is no automatic expiry.

## Updates

On first installation, or when upgrading an older App, Shell or pre-1.4.0 plugin runtime, run setup once. Keep the setup window open, quit clients when asked, then reopen Codex. Existing model choices, routing state, the original backup baseline, usage data and exports are preserved.

After that, compatible program updates need no Codex restart. The host must deliver the new plugin package first. The next Nexus command or trusted root routing hook stages the program in its own version directory, verifies it, then switches later calls to it. Running commands retain their old source directory. No new daemon or remote code downloader is installed.

Enter in Codex chat:

```text
tvlk-ai-router update check
tvlk-ai-router update prepare
tvlk-ai-router update rollback
```

- **check:** Show policy, package version, active runtime, previous runtime and any rollback hold.
- **prepare:** Explicitly try the live update. If configuration, dependency, launcher or data compatibility changed, open the existing waiting setup window.
- **rollback:** Switch to the previous compatible runtime. Keep configuration and usage unchanged. Hold automatic reactivation of the rolled-back version until explicit prepare or a newer release.

The initial runtime is version 1.4.0. To adopt this mechanism, older users still need one cold setup. Repeating setup on an already current version does not reinstall or enable disabled routing.

| Change | Codex exit needed? |
| --- | --- |
| Compatible program fixes, statistics or export changes | No; later calls use the new runtime |
| Compatible runtime rollback | No |
| First setup or migration from App/Shell/pre-1.4.0 | Once |
| Native model/agent settings, incompatible runtime/data changes | Maintenance setup; client-exit checks remain |
| Configuration or full backup restore | Yes, through the existing recovery flow |
| Host plugin registration, hooks or permissions | Depends on the host refresh/trust flow; not guaranteed live |

Automatic updates do not change model defaults or overwrite user choices. A candidate that fails validation does not replace the active version. Conflicting ownership, altered files and pending configuration recovery stop activation with a reason. Repeated attempts reuse verified staged files. Old releases are retained for running processes and recovery; this uses disk space.

A workspace admin can import the GitHub marketplace from `https://github.com/julian-ko/FPR-Nexus`; new workspace marketplaces have daily sync enabled. A local ZIP has no remote update source. Nexus activates packages already delivered by the host; marketplace timing and permissions remain under host control.

The public `releases/policy.json` endpoint carries version metadata only. Required updates limit Nexus activation, not direct Codex use, review, disable or recovery. A cold setup still verifies backups before configuration writes. Ordinary live updates create no full Codex backup because they leave Codex configuration and history untouched.

Official references: [Workspace marketplace sync](https://learn.chatgpt.com/docs/enterprise/plugin-management), [Local plugin updates](https://developers.openai.com/plugins/build/plugins), [Pricing](https://learn.chatgpt.com/docs/pricing).
