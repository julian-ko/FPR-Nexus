# Install FPR Nexus

Requires local Codex on macOS. This GitHub repo is public. Setup automatically finds an existing Python 3.11+ with `venv` and `ensurepip`, including the Codex bundled runtime when available. It does not download Python. If none is found, obtain an approved Python from IT and retry setup.

1. In Codex, send:

   > Install FPR Nexus from https://github.com/julian-ko/FPR-Nexus and run its setup. Replace my old router safely and keep my settings and backups.

2. Run the plugin's **Set up** action, or enter `tvlk-ai-router setup` in a new chat. Review and trust its hooks when prompted.

3. For a first install or an upgrade from before 1.4.0, follow the setup window prompt: quit Codex/ChatGPT, CLI sessions and the old Router app if open. Leave the window open; setup continues automatically. It preserves existing model choices, routing state, backups and usage files.

4. Reopen Codex, start a new chat, and enter `tvlk-ai-router status`.

No manual cleanup is needed for a verified App or Shell installation. Recognized leftovers from a failed Shell setup are archived automatically. If a conflict is reported, keep the files and share the error.

After this one-time setup, compatible feature updates activate on the next Nexus command or routing hook after Codex delivers the new plugin. No setup window or restart is needed for that runtime change. Native settings and incompatible migrations still require the exit check. If Codex has not refreshed the plugin's skills or hooks, follow its refresh prompt.

After a failed older setup, update the plugin and start a new **Set up** window. An old setup window or command file still runs its old copy. New Codex folders are backed up and preserved automatically; no manual classification is needed.

[Commands and recovery](OPERATIONS.md)
