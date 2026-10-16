---
name: tvlk-ai-router
description: Set up and manage the FPR Nexus plugin in local Codex. Use for router setup, help, configuration, usage review, enable, disable, backups and restore. Ordinary writing and coding do not trigger this management skill.
---

# FPR Nexus plugin

Resolve the plugin root from this loaded skill's absolute path: it is two directories above the `skills/tvlk-ai-router` directory. Invoke `bash "<absolute-plugin-root>/scripts/chat.sh" <arguments>` with local execution tools, substituting the resolved path. Do not assume `PLUGIN_ROOT` is exported in a normal shell tool; that variable is provided to plugin hooks.

| Request | Arguments |
|---|---|
| setup or runtime upgrade | `setup --open` |
| help | `help` |
| configuration | `show` |
| validate / export configuration | `config validate` / `config example` |
| status | `status` |
| usage | `review` / `review 30d` / `review since-install` |
| Nexus usage by task | `review all --scope nexus --group-by task` |
| usage by date / model | `review 30d --group-by date` / `review 30d --group-by model` |
| custom UTC dates | `review --from YYYY-MM-DD --to YYYY-MM-DD` |
| version check | `update check` |
| upgrade after refreshing the plugin | `update prepare` |
| backups | `backups` |
| apply / enable / disable | `request apply` / `request enable` / `request disable` |
| restore selected backup | `request restore --backup-id <id>` |
| cancel pending change | `cancel` |

Setup automatically checks existing Python installations, the router runtime and the Codex bundled runtime. Do not stop after checking only the default `python3`. For a verified interpreter outside these locations, invoke `setup --python "<absolute-python-path>" --open`. If discovery fails, follow the packaged setup Skill's dependency guidance.

Setup detects old installations and opens a setup window. Tell the user to quit Codex/ChatGPT and CLI sessions, leave the window open for automatic continuation, and reopen after completion. Setup verifies and migrates owned App/Shell installations, preserving user settings and historical backups. If the window cannot open, link the returned Setup-Router.command. Read-only commands run directly. Other changes return a pending request and a quoted Terminal command; pending means configuration has not changed. Do not execute cold configuration writes from chat, force-quit apps, edit state/request files or bypass process checks. After reopening, check status and start a new chat.

Unrecognized Codex Home content is backed up and preserved automatically during setup and normal config restore. A preserved_paths report is informational, not a setup error. Do not delete these paths or request manual classification. Unknown old Router leftovers, managed-file conflicts, unreadable backups and active clients remain blocking errors.

For uninstall, first run `review all` to retain final usage, then complete disable (or the explicitly selected restore) and verify it. Then use the client's plugin removal capability when the user has requested removal. Always keep `~/.local/share/fpr-nexus-history/`, backups and the durable recovery runtime. Removing plugin files alone does not undo model settings. Collection stops after removal; already collected records remain without automatic expiry.

For model changes, show the configuration path and edit only requested router.toml fields before queuing apply. Preserve other settings. Do not edit generated native roles. For restore, require an explicit backup ID; list choices if missing. Default to config scope. Only append `--scope full` for an explicit full-history restore; it rolls back worktrees and chat history.

Review updates the durable local ledger and saves one timestamped JSON/Markdown pair under `~/.local/share/fpr-nexus-history/exports/`. Keep both files after plugin removal. Link the returned files. The default output is tables; `--json` returns schema 1.0.0 with all usage and routing records. Show these five sections in the user's language:

1. Summary: UTC period, All/Nexus/unattributed scopes, turns, observations, tokens and estimated credits, plus uncached/cache/output splits. Nexus is part of All.
2. Model and reasoning effort: turns, uncached input, cached input, output and credits. Keep unknown efforts unknown.
3. UTC date, model, reasoning effort and task type: turns, tokens and credits. Group turn counts are not additive.
4. First five usage records. The JSON retains all records, including event IDs, parent/child links and routing intent. Selected settings do not prove actual execution.
5. Missing data and assumptions: missing tokens, unpriced events, unknown tasks/attribution, assumed Standard speed and rate versions. Credits are estimates, not bills or subscription quota. Cache is part of input; reasoning is part of output.

No local analysis, largest-contributor explanations or recommendations. No upload. Merge overlapping exports by `event_id`, not by adding snapshot totals. Amounts are decimal strings in JSON and rounded in tables. `--group-by` remains accepted for compatibility; all five sections are always included in this order. Task types come from recorded choices, roles or parent links, never guesses from model names or private text. Coverage scan counters describe whole files, not just the selected dates.

Trusted routing hooks provide an internal `record-route` command for new work. Use its supplied session identity and transcript, with fixed category/mode/reason labels; never invent IDs or save prompts. Recording failures leave attribution unknown and must not block the user's task. Do not backfill historical route choices from guesses. Records and usage remain local and survive plugin removal.

Version checks fetch only the public version policy, with no usage upload. `update prepare` opens setup only when the loaded plugin package is current. If the package is old, use the host's supported plugin refresh flow, start a new chat to load the updated skill, then retry. Do not edit cached plugin files or trust settings to bypass the check. A required update limits Nexus routing guidance and apply/enable operations; it cannot block direct Codex use. Keep help, review, disable and recovery available. Never claim a setup window waiting for client exit has completed.

Automatic routing is injected by enabled plugin hooks only after successful setup. Native subagents receive no further routing context. Disabling/removing the plugin stops new hook calls; it does not undo installed model/agent configuration or instructions already in an existing chat. For recovery without the plugin, invoke the durable local program under `~/.local/share/tvlk-ai-router-plugin/runtime/tvlk-ai-router` and stage a restore request, then use its returned manage.sh command.

This requires local file/tool access. Report unavailable tools honestly. Ordinary ChatGPT cloud cannot change this local configuration.
