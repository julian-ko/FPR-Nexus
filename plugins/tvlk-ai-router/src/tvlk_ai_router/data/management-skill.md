---
name: tvlk-ai-router
description: Manage the TVLK-OpenAI-Router Shell installation in local Codex chat. Use for router commands, configuration, usage review, help, enable, disable, backups and restore. Ordinary writing or coding requests do not trigger this workflow.
---

# Shell chat management

Local program: `__ENGINE_COMMAND__`. Invoke with local execution tools. It uses a private Python environment and installed source.

| User request | Arguments |
|---|---|
| `tvlk-ai-router`, help | `chat help` |
| configuration | `chat show` |
| status | `chat status` |
| backups | `chat backups` |
| review, 7 days | `chat review` |
| review, 30 days | `chat review 30d` |
| review since installation | `chat review since-install` |
| disable / enable / apply | `chat request disable` / `chat request enable` / `chat request apply` |
| restore a selected backup | `chat request restore --backup-id <id>` |
| cancel a pending request | `chat cancel` |

Run read-only commands directly and summarize actual results. For changes, create a pending request and give the exact returned Terminal command to the user. They must quit Codex/ChatGPT and run it in Terminal. Do not execute writes from chat, force-quit apps, bypass process checks, edit request JSON or claim a pending change succeeded. After reopening Codex, use status to confirm the result and ask them to start a new chat.

For restore, list backups and ask for an explicit backup ID if absent. Default to config scope. Only append `--scope full` when the user explicitly requests full historical state; explain that history and worktrees also roll back. Backup and restore preserve the recovery skill.

For model edits, use show to find router.toml, edit only the requested fields, then queue apply. Do not change generated agent files. Preserve other configuration and clarify unspecified settings.

Review saves statistics and timestamped JSON/Markdown pairs in `~/.local/share/fpr-nexus-history/`, outside the plugin and configuration backups. Preserve the directory during uninstall and recovery. Show five sections: summary with All/Nexus/unattributed scopes and token/credit splits; model plus reasoning effort; UTC date/model/effort/task; first five usage records; missing data and rate assumptions. Link both saved files. JSON schema 1.0.0 includes all records and decimal-string credit amounts; merge snapshots by event_id, not summary totals. Cache is part of input and reasoning is part of output. Unknown values stay unknown; selected intent is separate from actual journal execution. These are stored Standard credits estimates, not company bills or account quota. Do not produce local analysis, largest-contributor explanations, recommendations or uploads. Use --scope all|nexus, optional --from YYYY-MM-DD --to YYYY-MM-DD, and --json. The legacy --group-by flag remains accepted; all five sections are always shown in the fixed order. Run review before uninstall to retain final usage; collection stops when the plugin is removed.

Local tool/file access is required. Ordinary ChatGPT cloud cannot run this local tool or switch its model. Report unavailable execution honestly. There is no registered native slash command; `$tvlk-ai-router help` can explicitly invoke this skill.
