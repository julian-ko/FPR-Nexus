# Validation

Version 0.5.0 · 2026-10-13 · Asia/Singapore

Host: macOS, Apple Silicon. Python 3.12.14. No installation or configuration change was made to the user's live Codex Home.

## Scope

This independent plugin distribution reuses the 0.4.2 Shell source, backup engine, and offline dependency. Original App and Shell distributions and the user's installed configuration must remain unchanged.

## Verified checks

- 71 automated tests passed, including 64 retained/adapted router and Shell regressions and 7 plugin tests. A coordinator run passed the initial 70 tests; the final 71-test run also covers the instruction-file fix identified in review.
- Plugin setup and repeat setup in isolated user directories preserve the original baseline, installation time, edited model settings, and existing global AGENTS text. An absent AGENTS file stays absent through setup, apply, disable, enable, and restore. The plugin does not install a second shared management skill.
- Existing Shell ownership is refused by the plugin installer; existing App ownership guards remain covered by the retained suite.
- Hook checks cover valid root sessions, native and generic subagents, missing identity, disabled router state, configuration drift, and a runtime/plugin version mismatch. A real isolated hook subprocess produced the expected UserPromptSubmit JSON and no output for missing identity.
- Pending changes and restore use the durable runtime outside the plugin cache and retain plugin ownership.
- All five Bash scripts pass syntax checks. The management skill passes the official skill-creator validator.
- The actual Codex CLI added the local marketplace and installed `tvlk-ai-router@tvlk-ai-router` 0.5.0 in a temporary HOME and CODEX_HOME. The installed cache contained the skill, hook manifest, and source, and its isolated user configuration enabled the plugin.
- Documentation links were checked. A targeted text scan found no personal absolute paths or credential-like literals; this is not a full security audit.
- The previous 0.4.1 App, Team Pack, and Shell archives and the 0.4.2 Shell archive retained their recorded SHA-256 hashes.
- An independent targeted source review found no publication blockers. Its minor finding about creating an empty AGENTS file was fixed and covered by the final regression test.

## Limits

Successful setup tests use temporary user directories and mock the cold-client gate. They do not prove a successful install on a teammate's computer. Plugin trust, model availability, and organizational policies must be checked in the target client. Local usage review is not a billing integration.

The native CLI installation check proves marketplace discovery, cache installation, and enabled configuration. It does not prove hook trust or end-to-end model delegation in the desktop UI. Hooks intentionally stay silent when valid root-session metadata is unavailable. Disabling a plugin stops future hook loading at the host level; the already-written model and agent settings require an explicit router disable or restore operation.

The first plugin release refuses automatic migration from App or Shell installations. It requires an approved Python 3.11+ interpreter; its private environment still depends on that interpreter. Windows, Linux, Intel Macs, and other client versions were not tested.
