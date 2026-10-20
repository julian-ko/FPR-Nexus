# Commands and recovery

## Chat commands

| Command | Result |
| --- | --- |
| `tvlk-ai-router setup` | Update a compatible runtime, or open setup when maintenance is needed |
| `tvlk-ai-router help` | Show commands |
| `tvlk-ai-router status` | Installed state, models, conflicts and pending change |
| `tvlk-ai-router config show` | Configuration path and models |
| `tvlk-ai-router apply` | Apply edits to router.toml |
| `tvlk-ai-router disable` | Stop routing and undo active native settings |
| `tvlk-ai-router enable` | Enable routing again |
| `tvlk-ai-router backup list` | List and verify snapshots |
| `tvlk-ai-router restore <backup-id>` | Restore selected configuration |
| `tvlk-ai-router review since-install` | Local model and task-type usage |
| `tvlk-ai-router review all --scope nexus --group-by task` | Nexus-only task usage and estimated credits |
| `tvlk-ai-router review 30d --group-by date` | Daily totals in UTC |
| `tvlk-ai-router review --from 2026-10-01 --to 2026-10-15 --group-by model` | Model totals for an inclusive UTC date range |
| `tvlk-ai-router update check` | Fetch the public version policy; no usage upload |
| `tvlk-ai-router update prepare` | Activate the host-delivered update, or open safe setup for migration |
| `tvlk-ai-router update rollback` | Select the previous compatible runtime without changing settings |

Review accepts 7d, 30d, since-install and all. It imports statistics into a durable local database without changing Codex settings. Other inspection commands run directly in chat. Apply, enable, disable and restore return a pending request and a recovery command. Quit the clients before executing it. Pending is not completed. Full-history restore requires an explicit request; normal restore covers configuration.

## Migration

Setup checks App and Shell ownership before changing native settings. It verifies backups and manual changes, disables the old router, and moves the old program and duplicate Skill into a recovery archive. It then adopts the state and restores the previous routing status. Disabled and restored users stay in that state. It does not run the old program.

Model choices, historical backups, backup IDs and the original install date stay in place. Recovery copies of the removed App, Shell runtime and Skill stay at `~/.local/share/tvlk-ai-router-plugin/legacy/`. They do not run automatically.

Interrupted moves resume on the next setup. If setup fails after disabling the old router, routing stays disabled until setup succeeds. No backup is deleted. Unowned files, edited managed files, conflicting installs, invalid models, corrupt backups and pending changes stop migration. Resolve the reported conflict instead of deleting state.

Historical App/Shell snapshots remain usable. Restoring one does not recreate the shared Skill or permanent routing block; the plugin keeps ownership. The original pre-install baseline remains available.

## Files

| Path | Purpose |
| --- | --- |
| `~/.config/tvlk-ai-router/router.toml` | Editable models and rules |
| `~/.local/share/tvlk-ai-router/` | State, backups and pending changes |
| `~/.local/share/tvlk-ai-router-plugin/runtime/` | Private environment and recovery program |
| `~/.local/share/tvlk-ai-router-plugin/runtime/releases/` | Verified runtime versions, retained for running calls and rollback |
| `~/.local/share/tvlk-ai-router-plugin/runtime/active.json` | Current and previous runtime pointers, plus automatic-update hold |
| `~/.local/share/tvlk-ai-router-plugin/setup/` | Durable setup files |
| `~/.local/share/tvlk-ai-router-plugin/legacy/` | Inactive old program and Skill |
| `~/.local/share/fpr-nexus-history/usage.sqlite3` | Permanent collected statistics; kept after plugin removal |
| `~/.local/share/fpr-nexus-history/version-policy.json` | Last successfully fetched version policy |
| `~/.codex/agents/` | Generated native agents |

Backups may use a custom path. Migration accepts the original CODEX_HOME with standard router/shared directories; unexpected custom targets require recovery review.

## Update

For the GitHub marketplace channel, ask Codex to refresh the marketplace and plugin:

```sh
codex plugin marketplace upgrade tvlk-ai-router
codex plugin add tvlk-ai-router@tvlk-ai-router
```

Review changed hooks when prompted. First installs and pre-1.4 runtimes need one setup with clients closed. Later compatible updates activate on the next Nexus command or routing hook without a Nexus-required restart. Host skill/hook refresh is separate; follow Codex's refresh prompt if needed.

Since 1.1.0, `update check` reads `releases/policy.json` from this repository's main branch. `latest` is the available version; `minimum_supported` is the version required after `upgrade_deadline` (UTC). A null deadline applies the minimum immediately. Never raise the minimum before its package is available. The current policy advertises 1.4.1 and keeps 1.0.8 supported; no deadline has been imposed on teammates.

Background checks reuse a six-hour cache. A failed fetch keeps the last known policy and marks it stale; a client with no known policy reports unknown and continues. Explicit `update check` retries immediately. Old 1.0.8 installations have no policy reader and need one normal upgrade first.

`update prepare` checks the host-delivered package. For a compatible update, Nexus copies source to an immutable version directory, checks integrity, dependencies, generated native settings and the runtime/data contract, then atomically switches the active pointer. Running calls keep their original directory. Failed validation leaves the active version unchanged. Installation and configuration locks prevent overlapping writes; pending configuration recovery blocks activation. Settings, install date, baseline, routing state and usage exports are not rewritten by a live update.

`update rollback` checks and selects the previous compatible runtime. The rejected version is held back from automatic reactivation until explicit `update prepare` or a newer package arrives. Versions are retained and use disk space; there is no automatic pruning. If integrity is broken, use recovery rather than deleting state. Cold setup still verifies backups and waits for clients before configuration writes. Incompatible runtime/dependency/data contracts use this maintenance flow; new schema migrations require their own implementation and tests.

Release authors must increment the relevant `runtime.json` contract when launcher, native configuration, history schema or dependency compatibility changes. Compatible releases must continue to work with the installed stable launcher. An ordinary live update does not replace that launcher or its Python environment. Git marketplace and Plugin Creator are separate delivery channels. No server-selected code is downloaded or executed.

A required policy suppresses Nexus routing guidance and blocks install/apply/enable through the managed runtime. Review, help, disable and restore remain available. It does not revoke native model settings, erase old chat instructions, prevent direct Codex use, or stop a user from disabling this personal plugin. Company-wide mandatory enforcement requires managed devices/services.

Workspace administrators can import this repository under Admin > Plugins > Import marketplace; new marketplaces sync daily. Use a branch for future updates, not a fixed commit. Nexus checks the delivered package when called; there is no polling daemon or code downloader. A ZIP needs a newer package supplied manually. See [official marketplace sync](https://learn.chatgpt.com/docs/enterprise/plugin-management).

## Usage and estimates

Hooks schedule local collection at session start, prompts, turn completion and session end. Startup/prompt collection is throttled to five minutes; final collection bypasses that delay. Only changed journals are parsed. `review` also synchronizes before reporting, including all still-readable history on first import. Hook collection is best-effort; disabled/untrusted hooks, crashes and deleted-before-collection logs can leave gaps. Run `review all` before removal to capture final usage.

The ledger retains statistics indefinitely outside plugin/cache/backup roots. Uninstall and config/full restore do not delete it. It stores no prompts, code, replies or tool output. Removal stops collection; it does not collect new activity while uninstalled. A future installation reuses the existing ledger. Keep a personal backup of this directory if disk/device loss must be covered.

All means retained local user sessions, excluding system sessions and unidentifiable inherited history. Nexus is a subset attributed by a recorded routing choice, a custom agent role or a parent-turn link. Unattributed is not proof of non-Nexus. Task types use recorded choices and roles; unknown history is not inferred from text or model names. Date groups use usage-event UTC dates, including turns crossing midnight. Counts across date/model rows are not additive.

From 1.3.0, every review saves a JSON/Markdown pair in `~/.local/share/fpr-nexus-history/exports/<UTC timestamp>-<snapshot ID>/`. The five table sections cover summary, model/reasoning effort, UTC date/model/effort/task, first five records, and missing data. JSON schema 1.0.0 retains all records with decimal-string credits. The `--json` shape replaces the 1.2.0 flat report. The legacy `--group-by` flag remains accepted; all sections use the fixed order. Overlapping snapshots must be merged by event_id, not by adding totals. Saved estimates are not repriced. Pair creation is staged; failed writes preserve existing exports. No local analysis or upload runs.

Trusted root-session hooks ask the assistant to invoke the internal `chat record-route` command with the hook-provided transcript and session ID, task type, direct/delegated mode and fixed reason code. The command validates the root journal and active turn, writes only bounded metadata to the ledger, and preserves changed choices while deduplicating retries. It does not execute delegation or change Codex configuration. Journal metadata supplies actual model/effort and parent/child IDs; a selected model is not proof that it ran. Missing/disabled hooks or a skipped record leave attribution unknown. Coordinator activity includes reading, tools and summaries, not just classification. No automatic optimization advice is produced.

Estimated credits use the public Standard input/cached-input/output rates verified on 2026-10-15: [official rate card](https://learn.chatgpt.com/docs/pricing). Company billing is unknown. Cache is subtracted from input before applying the uncached rate; reasoning is already part of output. Unknown model prices, cache splits and explicit nonstandard speeds remain unpriced. Missing speed assumes Standard and is counted separately. No dollar conversion, tool charge, contract discount or subscription quota inference is made.

Historical imports use this default rate card as an estimate, not the historical invoice. Each event retains its original price version and estimate. Later releases do not silently reprice saved data. The report identifies unpriced events, partial turns, missing fields, turns without observations, rate versions and coverage gaps. Token totals and credits describe observed data only. Server usage upload is not implemented.

## Remove

Run `review all`, complete router disable or the selected restore, then uninstall the plugin in the client. Always keep `~/.local/share/fpr-nexus-history/`. Removing plugin files alone stops future hooks but leaves native settings. Start a new chat; old chats can retain earlier instructions.

If the plugin was removed first, recovery remains available:

```sh
"$HOME/.local/share/tvlk-ai-router-plugin/runtime/tvlk-ai-router" chat help
```

Request disable or restore and follow its returned command with clients closed. Keep backups until you no longer need them.

## Manual installation

For clients with the plugin CLI:

```sh
codex plugin marketplace add https://github.com/julian-ko/FPR-Nexus
codex plugin add tvlk-ai-router@tvlk-ai-router
```

Then follow [setup](INSTALL.md). Setup finds Python 3.11+ with venv/ensurepip automatically, including existing router and Codex runtimes. To select another approved interpreter, use `bash "<plugin-root>/scripts/chat.sh" setup --python /absolute/path/to/python3 --open`. Direct Terminal installation also accepts `install.sh --python /absolute/path/to/python3`. The pinned dependency installs offline; Python is not downloaded. No macOS security settings are changed.

Official reference: [Plugin packaging and onboarding](https://developers.openai.com/plugins/build/plugins).

## Files added by newer clients

Setup backs up unfamiliar Codex Home files and leaves them in place. `preserved_paths` is an informational list, not an error. Config restore keeps their current contents, including files added after the backup. Only an explicitly requested full restore rolls them back. Add a path to `additional_config_paths` only when you want it treated as configuration for normal restore.

Regular files are copied and verified. Symlinks are saved as links without following unknown external targets; sockets and other special files are recorded but not recreated. Unreadable or changing data still stops setup before configuration writes. Router ownership, managed-file conflicts and client-exit checks remain enforced.

Plugin cache links are always saved as links, without following their targets. Normal config restore keeps the current plugin cache. Incidental broken or cyclic resource links are preserved too; missing explicitly referenced configuration still requires correction. Another plugin's broken dependency is not a reason to delete its files before Router setup.
