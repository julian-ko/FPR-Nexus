# TVLK-OpenAI-Router

Version 0.5.0 · Personal Codex plugin · macOS

## What

One plugin helps your main assistant choose a specialist for each task. You keep one model configuration file, local backups, and chat commands for help, settings, and usage review.

| Role | Model | Reasoning |
| --- | --- | --- |
| Main assistant | GPT-6 Luna | medium |
| Coding | GPT-6.1 Sol | medium |
| Writing | GPT-6 Astra | low |
| Product and engineering plans | GPT-6 Astra | medium |
| Hard analysis | GPT-6 Astra | xhigh |

These are team defaults. They are not a claim that one setting is best for every task. Your account must have access to the selected models.

## Why

- Share one GitHub link with the team instead of sending a new App archive for each release.
- Keep model settings in one file and reuse the existing backup and restore engine.
- Let the plugin load short routing rules for new chats. The main model still decides which specialist to use.

The main assistant reads context, handles management commands, and reviews specialist results. It is not a zero-cost classifier. Plugin packaging does not by itself reduce token use.

## How

Repository: https://github.com/julian-ko/TVLK-OpenAI-Router

This repository is private. Each teammate needs read access and GitHub authentication on their own computer. A repository link does not grant access.

In a local Codex chat with command execution, ask:

> Install the tvlk-ai-router plugin from https://github.com/julian-ko/TVLK-OpenAI-Router, then guide me through tvlk-ai-router setup. Preserve my existing settings and backups.

The plugin source can also be added directly:

```sh
codex plugin marketplace add https://github.com/julian-ko/TVLK-OpenAI-Router
codex plugin add tvlk-ai-router@tvlk-ai-router
```

Restart the client and start a new chat. Review and trust the plugin hooks through the client when prompted. Then enter `tvlk-ai-router setup`.

**Installing the plugin and applying the model configuration are separate steps.** First-time setup requires an approved Python 3.11+ with `venv` and `ensurepip`. Setup returns a local Terminal command; quit Codex/ChatGPT before running it, then reopen the client. Python is not downloaded by this package. The bundled dependency is installed offline.

Read [INSTALL.md](INSTALL.md) before setup, updates, or removal. See [VALIDATION.md](VALIDATION.md) for what has actually been tested.

## Daily commands

Enter these in local Codex chat:

```text
tvlk-ai-router help
tvlk-ai-router config show
tvlk-ai-router status
tvlk-ai-router review since-install
tvlk-ai-router backup list
tvlk-ai-router disable
tvlk-ai-router enable
tvlk-ai-router restore <backup-id>
```

Read-only commands run in chat. Configuration changes use a pending request and a Terminal command after closing the client. They do not force-quit apps.

Usage review reads retained local and archived sessions, including non-router sessions. Cached input is part of input; reasoning output is part of output. Counts are not bills or account quotas. Unknown roles and missing data remain visible.

## Existing users

The App and Shell editions remain separate. This release refuses to overwrite an App-managed or Shell-managed installation. Keep using that edition until a migration path is available. Do not delete ownership records or backups to force setup.

Turning off the plugin stops future hook loading; it does not restore the default model or remove installed agent configuration. Existing chats can retain earlier instructions. Use the router's restore workflow before removing the plugin if you want to undo configuration changes.

## Source

The plugin lives in `plugins/tvlk-ai-router`. The marketplace catalog is `.agents/plugins/marketplace.json`. User configuration, runtime state, and backups live outside the plugin cache so a plugin refresh does not replace them.

No API proxy, hosted service, or external usage collector is included. See [third-party notices](plugins/tvlk-ai-router/THIRD-PARTY.md) for the bundled dependency.
