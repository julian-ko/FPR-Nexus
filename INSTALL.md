# Install TVLK-OpenAI-Router

Requires local Codex on macOS and access to this private GitHub repo. Setup automatically finds an existing Python 3.11+ with `venv` and `ensurepip`, including the Codex bundled runtime when available. It does not download Python. If none is found, obtain an approved Python from IT and retry setup.

1. In Codex, send:

   > Install the plugin from https://github.com/julian-ko/TVLK-OpenAI-Router and run its setup. Replace my old router safely and keep my settings and backups.

2. Run the plugin's **Set up** action, or enter `tvlk-ai-router setup` in a new chat. Review and trust its hooks when prompted.

3. Follow the setup window prompt: quit Codex/ChatGPT, CLI sessions and the old Router app if open. Leave the setup window open; it continues automatically when the clients exit. Setup checks the old installation, keeps backups, removes the old program and applies the plugin settings.

4. Reopen Codex, start a new chat, and enter `tvlk-ai-router status`.

No manual cleanup is needed for a verified App or Shell installation. Recognized leftovers from a failed Shell setup are archived automatically. If a conflict is reported, keep the files and share the error.

After a failed older setup, update the plugin and start a new **Set up** window. An old setup window or command file still runs its old copy. New Codex folders are backed up and preserved automatically; no manual classification is needed.

[Commands and recovery](OPERATIONS.md)
