# FPR Nexus

Version 1.4.2 · Codex plugin · macOS

Formerly TVLK-OpenAI-Router. Existing installations keep the same plugin identity, `tvlk-ai-router` commands, settings and backups.

## What

A self-contained plugin for task routing, model settings, local usage review and backup recovery. The plugin includes its own setup and recovery program; an older App or Shell package is not required.

| Task | Model | Reasoning |
| --- | --- | --- |
| Main assistant | GPT-6 Luna | medium |
| Coding | GPT-6.1 Sol | medium |
| Writing | GPT-6 Astra | low |
| Product and engineering plans | GPT-6 Astra | medium |
| Hard analysis | GPT-6 Astra | xhigh |

These are team defaults, not official best settings for every task. Your account must support them. Existing users keep their own model choices.

## Why

- One GitHub link for the team. No separate App package.
- One editable file for models, reasoning and routing rules.
- Verified backups before changes, with disable and restore commands.
- New client folders are backed up and kept as they are; they do not need a Router update.
- A setup check replaces the old router without losing settings or backups.
- After one setup, compatible feature updates need no client restart.

The main assistant reads the request and delegates work. It also reads context and reviews the result, so its token use is more than a short classification call.

## How

[Install in four steps](INSTALL.md).

```text
First / old install → Wait for exit → Back up → Migrate → Keep routing state

Later update → Check compatibility → Switch runtime → Keep working

Request → Luna → Coding / Writing / Product / Analysis → Result
```

Setup runs before native model configuration is applied. The host installs plugin files first; it does not provide a pre-install uninstall hook. Hooks only start routing after successful setup and user trust. A restart is needed for new model settings.

Enter these commands in a local Codex chat:

```text
tvlk-ai-router help
tvlk-ai-router config show
tvlk-ai-router status
tvlk-ai-router apply
tvlk-ai-router disable
tvlk-ai-router enable
tvlk-ai-router backup list
tvlk-ai-router restore <backup-id>
tvlk-ai-router review since-install
```

Every review now saves a timestamped JSON/Markdown pair under `~/.local/share/fpr-nexus-history/exports/`. The five table sections cover summary, model plus reasoning effort, UTC date/model/effort/task, first five usage records, and missing data. JSON includes every usage record, routing evidence and decimal-string credits. All/Nexus/unattributed scopes remain separate. Merge overlapping exports by event_id, not by adding totals. No local analysis or upload runs.

Statistics and route records stay outside the plugin with no automatic expiry. Credits use the public Standard rate card, not a company invoice or subscription quota. Unknown historical tasks stay unknown. No usage is uploaded and no automatic optimization advice is generated. [Read the short guide](plugins/tvlk-ai-router/USAGE-AND-UPDATES.md).

Version checks read a small public policy file. After Codex delivers the new plugin, the next Nexus command or routing hook activates a compatible runtime. `tvlk-ai-router update prepare` checks explicitly; `tvlk-ai-router update rollback` selects the previous compatible runtime. Running calls finish on their original version. Native settings, incompatible data changes and first/old installations still use the setup window and client-exit check. A minimum-version policy limits Nexus entry points; it does not control direct Codex use.

The repository is public. This plugin requires local tools; ordinary ChatGPT cloud chats cannot control local model settings.

Workspace admins can enable GitHub marketplace sync for plugin delivery. Nexus activates only packages delivered by the host; it installs no background downloader. A local ZIP needs a newer package to be supplied. Host skill/hook refresh is separate and may require a new chat or client restart.

[Commands, updates and recovery](OPERATIONS.md) · [Validation](VALIDATION.md) · [Third-party notices](plugins/tvlk-ai-router/THIRD-PARTY.md)
