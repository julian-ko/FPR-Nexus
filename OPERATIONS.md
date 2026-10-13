# Commands and recovery

## Chat commands

| Command | Result |
| --- | --- |
| `tvlk-ai-router setup` | Detect the installed edition and open setup |
| `tvlk-ai-router help` | Show commands |
| `tvlk-ai-router status` | Installed state, models, conflicts and pending change |
| `tvlk-ai-router config show` | Configuration path and models |
| `tvlk-ai-router apply` | Apply edits to router.toml |
| `tvlk-ai-router disable` | Stop routing and undo active native settings |
| `tvlk-ai-router enable` | Enable routing again |
| `tvlk-ai-router backup list` | List and verify snapshots |
| `tvlk-ai-router restore <backup-id>` | Restore selected configuration |
| `tvlk-ai-router review since-install` | Local model and task-type usage |

Review also accepts 7d and 30d. Read-only commands run in chat. Apply, enable, disable and restore return a pending request and a recovery command. Quit the clients before executing it. Pending is not completed. Full-history restore requires an explicit request; normal restore covers configuration.

## Migration

Setup checks App and Shell ownership before changing native settings. It verifies backups and manual changes, disables the old router, and moves the old program and duplicate Skill into a recovery archive. It then adopts the state and enables plugin routing. It does not run the old program.

Model choices, historical backups, backup IDs and the original install date stay in place. Recovery copies of the removed App, Shell runtime and Skill stay at `~/.local/share/tvlk-ai-router-plugin/legacy/`. They do not run automatically.

Interrupted moves resume on the next setup. If setup fails after disabling the old router, routing stays disabled until setup succeeds. No backup is deleted. Unowned files, edited managed files, conflicting installs, invalid models, corrupt backups and pending changes stop migration. Resolve the reported conflict instead of deleting state.

Historical App/Shell snapshots remain usable. Restoring one does not recreate the shared Skill or permanent routing block; the plugin keeps ownership. The original pre-install baseline remains available.

## Files

| Path | Purpose |
| --- | --- |
| `~/.config/tvlk-ai-router/router.toml` | Editable models and rules |
| `~/.local/share/tvlk-ai-router/` | State, backups and pending changes |
| `~/.local/share/tvlk-ai-router-plugin/runtime/` | Private environment and recovery program |
| `~/.local/share/tvlk-ai-router-plugin/setup/` | Durable setup files |
| `~/.local/share/tvlk-ai-router-plugin/legacy/` | Inactive old program and Skill |
| `~/.codex/agents/` | Generated native agents |

Backups may use a custom path. Migration accepts the original CODEX_HOME with standard router/shared directories; unexpected custom targets require recovery review.

## Update

Ask Codex to refresh the marketplace and plugin, then run setup:

```sh
codex plugin marketplace upgrade tvlk-ai-router
codex plugin add tvlk-ai-router@tvlk-ai-router
```

Restart and review changed hooks. Setup preserves your model choices and original backup baseline.

## Remove

Complete router disable or the selected restore, then uninstall the plugin in the client. Removing plugin files alone stops future hooks but leaves native settings. Start a new chat; old chats can retain earlier instructions.

If the plugin was removed first, recovery remains available:

```sh
"$HOME/.local/share/tvlk-ai-router-plugin/runtime/tvlk-ai-router" chat help
```

Request disable or restore and follow its returned command with clients closed. Keep backups until you no longer need them.

## Manual installation

For clients with the plugin CLI:

```sh
codex plugin marketplace add https://github.com/julian-ko/TVLK-OpenAI-Router
codex plugin add tvlk-ai-router@tvlk-ai-router
```

Then follow [setup](INSTALL.md). Setup finds Python 3.11+ with venv/ensurepip automatically, including existing router and Codex runtimes. To select another approved interpreter, use `bash "<plugin-root>/scripts/chat.sh" setup --python /absolute/path/to/python3 --open`. Direct Terminal installation also accepts `install.sh --python /absolute/path/to/python3`. The pinned dependency installs offline; Python is not downloaded. No macOS security settings are changed.

Official reference: [Plugin packaging and onboarding](https://developers.openai.com/plugins/build/plugins).
