# TVLK-OpenAI-Router

Version 1.0.2 · Personal Codex plugin · macOS

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

Usage review reads retained local sessions, including non-router sessions. Cached input is included in input; reasoning is included in output. These are local usage records, not bills or account quotas. Missing data and unknown task types remain visible.

The repository is private: teammates need read access and GitHub authentication. This plugin requires local tools; ordinary ChatGPT cloud chats cannot control local model settings.

[Commands, updates and recovery](OPERATIONS.md) · [Validation](VALIDATION.md) · [Third-party notices](plugins/tvlk-ai-router/THIRD-PARTY.md)
