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

For review, show recorded models, roles and coverage without prompts. Turns are not questions or API calls. Missing tokens remain unknown; shares cover observed local tokens only. A multi-model turn counts once overall. Local usage can include manual sessions; costs and account quota are outside scope.

Local tool/file access is required. Ordinary ChatGPT cloud cannot run this local tool or switch its model. Report unavailable execution honestly. There is no registered native slash command; `$tvlk-ai-router help` can explicitly invoke this skill.
