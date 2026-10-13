# Validation

Version 1.0.1 · 2026-10-13 · macOS Apple Silicon · Python 3.12.14

## Verified

- 86 automated tests pass. Five new checks cover automatic waiting, clients restarting during the wait, continuation without keyboard input, cancellation, detection failure and propagation of installer failure. The retained tests verify that active clients still block configuration writes.
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

Setup needs an approved Python 3.11+ interpreter. The private environment depends on that interpreter. Other operating systems, Intel Macs and organizational policy combinations were not tested.

The plugin host installs plugin files before onboarding. Legacy removal happens during setup, before native plugin settings are applied. Removing the plugin alone does not undo model configuration; use disable or restore first. Local usage review is not billing or account-quota measurement.
