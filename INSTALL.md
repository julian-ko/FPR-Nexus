# Install and manage the plugin

## Before you start

- Use local Codex on macOS with file and command access.
- Ask the repository owner for read access to `julian-ko/TVLK-OpenAI-Router`. Sign in to GitHub on this computer.
- Use an approved Python 3.11+ with `venv` and `ensurepip`. The plugin does not install Python, use `sudo`, or change macOS security settings.
- Make sure your account can use the configured models. Model access is separate from plugin access.
- If you already use the App or Shell edition, keep using it. This release does not migrate that installation.

## Install the plugin

Give this request to Codex:

> Install tvlk-ai-router from https://github.com/julian-ko/TVLK-OpenAI-Router and guide me through setup. Preserve existing settings and backups.

Codex can add the source and install the plugin with:

```sh
codex plugin marketplace add https://github.com/julian-ko/TVLK-OpenAI-Router
codex plugin add tvlk-ai-router@tvlk-ai-router
```

The marketplace and plugin are both named `tvlk-ai-router`. In the Plugins directory, the display name is TVLK-OpenAI-Router. Installing from a private repository still requires your own GitHub access.

Restart the client and start a new chat. Review and trust the plugin's hooks when prompted by the client. Installing or enabling a plugin does not automatically trust its hooks. Company settings may limit plugins or script execution.

## First setup

1. Enter `tvlk-ai-router setup` in the new chat.
2. Read the returned command and prerequisites. If Python is missing, provide an approved Python 3.11+ interpreter.
3. Finish active work and quit all Codex/ChatGPT clients.
4. Run the returned command in Terminal. It prepares a private environment, backs up configuration, and applies the model and agent settings.
5. Reopen Codex and start a new chat. Run `tvlk-ai-router status` and `tvlk-ai-router config show`.

The cold-client check prevents configuration changes while the client is running. A pending request is not a completed change. Setup does not force-quit applications.

## Files and updates

| Location | Purpose |
| --- | --- |
| `~/.config/tvlk-ai-router/router.toml` | Your editable model and routing settings |
| `~/.local/share/tvlk-ai-router/` | State, verified backups, and pending changes |
| `~/.local/share/tvlk-ai-router-plugin/runtime/` | Private environment and recovery program |
| `~/.codex/agents/` | Generated native agent files |
| `~/.codex/config.toml` | Default model and agent settings |

These are the normal user paths. If the installation reports a custom location, use its reported path. Backup paths are also shown by `tvlk-ai-router backup list` and may be configured separately.

Keep the unified configuration and backup storage outside the plugin cache. Update model settings through `tvlk-ai-router config show`, edit the requested values, then use `tvlk-ai-router apply` and finish the returned change request after closing the client.

To refresh the plugin source:

```sh
codex plugin marketplace upgrade tvlk-ai-router
codex plugin add tvlk-ai-router@tvlk-ai-router
```

Restart the client and review any changed hooks. If the plugin reports that its installed runtime is older than the plugin, run `tvlk-ai-router setup` again and follow the same cold-client steps. Refreshing plugin files alone does not apply the new runtime or replace your selected models. Reinstall keeps the existing configuration and original backup baseline.

## Disable, restore, and remove

- **Stop routing and undo active router settings:** enter `tvlk-ai-router disable`, close the client, and run the returned management command. Verify status after reopening.
- **Restore a selected backup:** enter `tvlk-ai-router backup list`, choose a backup, then `tvlk-ai-router restore <backup-id>`. Normal restore covers configuration. Full restore also affects historical runtime data and must be requested explicitly.
- **Disable the plugin in the Plugins directory:** this stops future plugin hook loading, but leaves the model settings, native agents, runtime, and backups on disk. Start a new chat; old chats can retain earlier instructions.
- **Remove the plugin:** complete disable or restore first if you want to undo its configuration, then uninstall it from Plugins. Keep backups and the recovery runtime until you no longer need them.

If you removed the plugin before restoring, the durable recovery program remains available:

```sh
"$HOME/.local/share/tvlk-ai-router-plugin/runtime/tvlk-ai-router" chat help
```

Use that program to list backups or request a change, and follow its returned `manage.sh` command after quitting the client. Do not edit state files or remove ownership markers to bypass checks.

## Troubleshooting

| Message or symptom | Action |
| --- | --- |
| Repository not found | Verify the GitHub account, read access, and private-repository authentication. |
| Python missing or too old | Choose an approved Python 3.11+ with `venv` and `ensurepip`; do not rerun with system Python if it fails the check. |
| App/Shell installation detected | Keep using that edition. Automatic migration is not included. |
| Clients are still running | Finish work and quit them before applying the returned change command. |
| Hooks are not trusted | Review the plugin hooks in the client and trust them if permitted by your company. |
| Config changed outside the router | Inspect the difference before applying or restoring; drift checks intentionally stop overwrites. |
| Unclassified files | Keep the files. Share the path names for classification review; do not label runtime data as configuration just to bypass the check. |

## Team sharing

Send the GitHub repository link and this guide. The repository owner must grant each teammate access. This plugin is a local Codex integration; it does not configure ordinary ChatGPT cloud chats or change their model.

Official references: [Plugin packaging](https://developers.openai.com/plugins/build/plugins), [Hooks](https://learn.chatgpt.com/docs/hooks), and [Native subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
