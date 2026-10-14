---
name: setup
description: Set up or upgrade the TVLK router plugin when the user requests installation or runs plugin onboarding. Detect and migrate an older router before activating the plugin.
---

# Set up TVLK-OpenAI-Router

Resolve the plugin root from this file at `<root>/skills/setup/SKILL.md`.
Run `bash "<root>/scripts/chat.sh" setup --open`. The launcher finds a usable Python automatically, including an existing router runtime or the Codex bundled runtime when available. It checks for an existing installation and opens a durable setup file in Terminal. It does not change live Codex settings.

Tell the user only the next steps: finish work, quit all Codex/ChatGPT clients and the old Router app if open, leave the setup window open while it waits and continues automatically, then reopen Codex and start a new chat. Do not force-quit clients or run the cold installation inside this chat. If Terminal cannot open, link the exact returned Setup-Router.command file for double-clicking. Do not reject setup based only on `python3 --version`. If discovery fails, use the host's workspace-dependencies tool when available to locate its Python, then retry `bash "<root>/scripts/chat.sh" setup --python "<verified-python-path>" --open`. It must support Python 3.11+, venv and ensurepip. If none is available, ask the user to obtain an approved Python installation; do not claim setup completed.

The installer verifies old ownership and backups before disabling and archiving the previous App/Shell program and shared Skill. A recognized failed Shell 0.4.1/0.4.2 bootstrap with no saved state, configuration, backups or pending transactions is archived automatically after clients exit. Its marker and any remaining wrappers must match the shipped files; unknown leftovers still stop setup. Existing models, router.toml, backups and the original install date are preserved. Unknown files inside an old Router installation, changed managed files, ownership conflicts or unverified backups still stop migration; do not delete them to bypass the check. Unrecognized files elsewhere in Codex Home (such as packages or new client directories) are backed up and preserved automatically. They do not need manual classification and do not block setup. Preserve these files; do not add them to additional_config_paths unless the user wants them treated as configuration restore targets. Retrying setup resumes an interrupted migration.

After reopening, run `bash "<root>/scripts/chat.sh" status` and `bash "<root>/scripts/chat.sh" config show`. Report configuration state separately from runtime model verification. If hooks need trust, direct the user to the client prompt; never edit trust settings automatically.
