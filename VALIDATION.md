# Validation

Version 1.0.8 · 2026-10-14 · macOS Apple Silicon · Python 3.12.14

## Verified

- Version 1.0.8 renames the display name, onboarding and management UI to FPR Nexus. Plugin identity, CLI command, runtime/config/backup paths and legacy migration markers remain unchanged.

- Version 1.0.7 fixes the reported context-mode node-which symlink failure. Plugin cache contents remain in snapshots, but their symlink targets are not followed and config restore preserves the cache. Incidental broken/cyclic links in linked resources are saved as links; missing explicitly referenced configuration still stops setup. Tests cover the exact dependency layout, valid external package links, cycles, linked Skills, explicit missing targets and cache preservation.
- A read-only preflight on the user's actual Codex Home completed: three snapshot roots, 1,813,798,579 regular-file bytes, and matching model availability. No configuration was written during this check.
- The actual 1.0.5 distribution ZIP reproduced both reported path errors in a temporary HOME. The 1.0.6 installer then continued from that failed runtime, reused its real Python environment and installed the offline dependency. Repeat setup, config validation, disable, enable and baseline restore passed through isolated CLI subprocesses. The original baseline, install time, user instructions, unrelated settings, new folders and previously archived Shell program were preserved. Only client detection was mocked in the child CLI; model availability used a fixture cache.
- Unrecognized Codex Home content no longer needs a per-name allowlist. Setup, validation and legacy migration include it in verified snapshots; config restore preserves its current state. Full restore remains explicit. Known configuration, declared extra paths and external configuration references retain their restore behavior. Opaque TOML files are not interpreted as configuration.
- Regression checks cover packages, tui-thread-reference-capabilities, arbitrary future paths, malformed opaque TOML, broken symlinks, sockets, changed and newly added content, explicit config paths, full restore, and unreadable data. Retry after the previous release's classification failure reuses the private Python environment. App/Shell migration fixtures also contain unfamiliar client files. The teammate's actual directory contents were not inspected.
- 111 automated tests pass. Retained checks cover failed Shell detection, read-only preparation, lossless archival, fresh installation, unknown history, edited files, symlinks, client/installer locks, interrupted moves, archive collisions, Python discovery, terminal progress and client checks before configuration writes.
- Shell 0.4.1/0.4.2 bootstrap leftovers are accepted only with the exact ownership marker and known remaining wrapper hashes, no installed source, and no saved configuration, backups, transactions or native router markers. The whole runtime is renamed to a recovery archive after the cold-client check and under both router and Shell installer locks. No old executable runs and no backup is deleted.
- On the development host, the default Python is 3.9.6; automatic discovery selects the existing router interpreter. Codex's bundled Python 3.12.14 also passed a real temporary venv creation and offline tomlkit installation. No live user configuration was changed.
- Terminal setup reuses one progress line across byte-processing stages. Percentages describe the current stage. Redirected output keeps plain log lines; native-launcher JSON progress events remain unchanged.
- The independent setup window waits for two consecutive clear process scans, then starts installation automatically. It shares client detection with the write guard; the installer still checks clients before writing. Waiting does not initialize the private environment or change router configuration.
- New setup and repeat setup preserve user settings, baseline backups and install time. Global instructions remain unchanged by plugin setup; no duplicate shared Skill is created.
- App and Shell migration fixtures cover enabled, disabled and restored states, missing configuration after baseline restore, edited Skills, corrupt backups, active clients, interrupted moves and changed archived files.
- Old programs are moved to the recovery archive. Router configuration and historical backup bytes remain in place. Migration retries finish remaining moves; ambiguous ownership stops before removal.
- Restoring an active App/Shell snapshot keeps plugin ownership and removes the legacy routing block. It does not recreate the old shared Skill. Restoring the original baseline and then enabling remains supported.
- A separate compatibility smoke check used the actual 0.4.2 Shell source to generate an installation in a temporary user directory. Migration to 1.0.0 preserved its original baseline, removed its old runtime and shared Skill paths, and left no managed-file drift.
- The actual Codex CLI installed the local marketplace plugin as version 1.0.0 in an isolated HOME/CODEX_HOME. Both manifests, the packaged onboarding Skill and the hook files were present. This did not create router configuration before setup.
- A remote GitHub check also downloaded and installed 1.0.0 from the private repository in a temporary HOME. The downloaded setup generated its durable command file without changing router configuration. The check used the owner's existing SSH authentication through a process-local Git URL rewrite.
- The prepared setup file passes Bash syntax validation, survives independently of the plugin cache, preserves CODEX_HOME and does not mutate router state during preparation.
- All four Bash scripts and the shell launcher pass syntax validation. Both Skills pass the official skill-creator validator.
- Hook tests cover root session metadata, subagent exclusion, disabled routing, managed-file drift and version mismatch. A real isolated hook subprocess returned the expected JSON.
- Usage tests retain cumulative-event deduplication, inherited-token handling, model switches, cached/reasoning accounting and partial-data reporting.

## Limits

Migration tests use temporary user directories, fixture model availability and a mocked cold-client gate. The App migration fixture mocks signature validation; it does not exercise a real installed App bundle. The normal process check and App verification code remain enabled in shipped setup.

The CLI check proves marketplace discovery and cache installation. It does not prove the desktop Set up button, Terminal opening, hook trust or end-to-end model delegation on a teammate's computer. Those require the target client and account.

Setup needs a usable Python 3.11+ interpreter with venv and ensurepip. It checks existing installations and the Codex bundled path when available; it does not download Python. The private environment depends on that interpreter, so removing its base Python can break it. Bundled runtime availability and location may differ on other clients; setup also accepts an explicit approved path. Other operating systems, Intel Macs and organizational policy combinations were not tested.

The plugin host installs plugin files before onboarding. Legacy removal happens during setup, before native plugin settings are applied. Removing the plugin alone does not undo model configuration; use disable or restore first. Local usage review is not billing or account-quota measurement.
