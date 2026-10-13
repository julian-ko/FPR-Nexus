---
name: setup
description: Set up or upgrade the TVLK router plugin when the user requests installation or runs plugin onboarding. Detect and migrate an older router before activating the plugin.
---

# Set up TVLK-OpenAI-Router

Resolve the plugin root from this file at `<root>/skills/setup/SKILL.md`.
Run `bash "<root>/scripts/chat.sh" setup --open`. This checks for an existing installation and opens a durable setup file in Terminal. It does not change live Codex settings.

Tell the user only the next steps: finish work, quit all Codex/ChatGPT clients, press Enter in the setup window, then reopen Codex and start a new chat. Do not force-quit clients or run the cold installation inside this chat. If Terminal cannot open, link the exact returned Setup-Router.command file for double-clicking. If Python is unavailable, help locate an approved Python 3.11+ with venv/ensurepip; do not claim setup completed.

The installer verifies old ownership and backups before disabling and archiving the previous App/Shell program and shared Skill. Existing models, router.toml, backups and the original install date are preserved. Unknown or manually changed files stop migration with a specific error; do not delete them to bypass the check. Retrying setup resumes an interrupted migration.

After reopening, run `bash "<root>/scripts/chat.sh" status` and `bash "<root>/scripts/chat.sh" config show`. Report configuration state separately from runtime model verification. If hooks need trust, direct the user to the client prompt; never edit trust settings automatically.
