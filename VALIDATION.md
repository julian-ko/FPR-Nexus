# Validation

Version 1.0.4 · 2026-10-13 · macOS Apple Silicon · Python 3.12.14

## Verified

- 105 automated tests pass. Eight new checks cover failed Shell detection, read-only preparation, lossless archival, fresh installation, unknown history, edited files, symlinks, client/installer locks, interrupted moves and archive collisions. The retained tests cover Python discovery, terminal progress and client checks before configuration writes.
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
