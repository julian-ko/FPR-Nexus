# FPR Nexus

Version 1.2.0 · Codex plugin · macOS

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

The main assistant reads the request and delegates work. It also reads context and reviews the result, so its token use is more than a short classification call.

## How

[Install in four steps](INSTALL.md).

```text
Setup → Check old version → Verify backups → Remove old program → Enable plugin

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

One review now shows All vs Nexus vs unattributed usage, uncached/cache/output tokens and credit splits, models, task types, daily trends, execution roles and missing data. Future routing choices record fixed task/reason labels and selected settings; journals supply actual model usage and parent/child links. A choice is not proof that the child ran. Coordinator usage includes context, tools and summaries, not only classification.

Statistics and route records stay outside the plugin with no automatic expiry. Credits use the public Standard rate card, not a company invoice or subscription quota. Unknown historical tasks stay unknown. No usage is uploaded and no automatic optimization advice is generated. [Read the short guide](plugins/tvlk-ai-router/USAGE-AND-UPDATES.md).

Version checks read a small public policy file. Refresh the plugin in Codex, then enter `tvlk-ai-router update prepare` to open the existing safe setup flow. A minimum-version policy limits Nexus entry points; it does not control direct Codex use. Existing 1.0.8 users need one normal upgrade before these checks exist.

The repository is public. This plugin requires local tools; ordinary ChatGPT cloud chats cannot control local model settings.

[Commands, updates and recovery](OPERATIONS.md) · [Validation](VALIDATION.md) · [Third-party notices](plugins/tvlk-ai-router/THIRD-PARTY.md)
