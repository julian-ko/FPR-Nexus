"""Cold migration of owned App/Shell installs; backups never move or disappear."""
import contextlib
import json
import os
from pathlib import Path

from .config import RouterError, json_bytes, parse
from .desktop import verify_app, request_status
from .manager import Manager
from .storage import atomic, entry, inventory, lock, no_symlink_parents, quiet_check, recover


@contextlib.contextmanager
def legacy_environment():
    saved = {k: os.environ.pop(k, None) for k in ("TVLK_ROUTER_SHELL_ROOT", "TVLK_ROUTER_BACKEND")}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def locations():
    home = Path.home()
    return {"application": home / "Applications/TVLK-OpenAI-Router.app",
            "shell-runtime": home / ".local/share/tvlk-ai-router-shell/runtime",
            "management-skill": home / ".agents/skills/tvlk-ai-router"}


def tree_signature(root):
    return {str(Path(path).relative_to(root)): value for path, value in inventory([root]).items()}


def migrate(runtime):
    """Resume after interruption. A failed migration leaves routing disabled, not half enabled."""
    runtime = Path(runtime)
    journal_path = runtime.parent / "migration.json"
    archive = runtime.parent / "legacy"
    data = Path.home() / ".local/share/tvlk-ai-router"
    paths = locations()
    for p in (journal_path, archive, data, *paths.values()):
        no_symlink_parents(p)
    state_path = data / "state.json"
    state = json.loads(state_path.read_bytes()) if state_path.exists() else None
    if state and state.get("installation_backend") == "plugin":
        if state.get("shell_runtime") != str(runtime):
            raise RouterError("Another plugin runtime owns this configuration", 4)
        if any(p.exists() for p in paths.values()):
            raise RouterError("Unexpected legacy files beside a plugin installation; no files were removed", 4)
        return
    if not state:
        if journal_path.exists() or any(p.exists() for p in paths.values()):
            raise RouterError("Legacy files have no ownership state. Keep them and request recovery before setup", 4)
        return
    quiet_check(include_router=True)
    if state.get("installation_backend") not in (None, "shell"):
        raise RouterError("Unsupported previous installation backend", 4)
    expected_targets = [str(Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().absolute()),
                        str(Path.home() / ".config/tvlk-ai-router"), str(Path.home() / ".agents")]
    if state.get("targets") != expected_targets:
        raise RouterError("Previous installation has custom targets; use its original CODEX_HOME and user paths", 4)
    with lock(data), legacy_environment():
        recover(data)
        m = Manager(*expected_targets[:2], str(data), expected_targets[2])
        if request_status(m)["status"] in ("pending", "running"):
            raise RouterError("Finish or cancel the pending router change before migration", 4)
        if journal_path.exists():
            journal = json.loads(journal_path.read_bytes())
            if journal.get("targets") != expected_targets or journal.get("runtime") != str(runtime) or not isinstance(journal.get("items"), list):
                raise RouterError("Migration record does not match this installation", 4)
            if any(name not in paths for name in journal["items"]):
                raise RouterError("Unknown path in migration record", 4)
        else:
            if archive.exists():
                raise RouterError("An unowned migration archive already exists", 4)
            if m.drift():
                raise RouterError("Legacy configuration has manual changes; resolve them before migration", 4)
            # Validate all old executables and the Skill before any configuration write.
            app, shell, skill = (paths[k] for k in ("application", "shell-runtime", "management-skill"))
            backend = m.state.get("installation_backend")
            if (backend is None and shell.exists()) or (backend == "shell" and app.exists()):
                raise RouterError("Multiple legacy installations found; no files were removed", 4)
            if app.exists():
                verify_app(app)
            if backend == "shell":
                if m.state.get("shell_runtime") != str(shell):
                    raise RouterError("Unrecognized Shell runtime path", 4)
                marker = shell / "shell-installation.json"
                no_symlink_parents(marker)
                if not marker.is_file() or json.loads(marker.read_bytes()) != {"runtime": str(shell), "distribution": "shell"}:
                    raise RouterError("Shell ownership marker is missing or changed", 4)
            if skill.exists():
                known = m.state.get("management_hashes", {})
                if set(p.name for p in skill.iterdir()) != {"SKILL.md"} or entry(skill / "SKILL.md").get("sha256") != known.get(str(skill / "SKILL.md")):
                    raise RouterError("Legacy management Skill was edited; no files were removed", 4)
            backups = m.backups()
            if not backups or any(not b["verified"] for b in backups):
                raise RouterError("Legacy backups could not be verified; migration stopped", 4)
            m.change("disable", dry=True)
            if m.source.exists():
                _, config = m.config()
            else:
                from importlib.resources import files
                config = parse(files("tvlk_ai_router").joinpath("data/router.example.toml").read_bytes())
                config["backup"]["directory"] = str(m.store())
            report = m.report(config)
            if report["unknown_configuration"] or report["model_check"]["status"] != "cache_matched":
                raise RouterError("Resolve configuration classification and model availability before migration", 4)
            journal = {"schema": 1, "runtime": str(runtime), "targets": expected_targets,
                       "items": [k for k, p in paths.items() if p.exists()], "phase": "prepared",
                       "previous_state": m.state,
                       "signatures": {k: tree_signature(p) for k, p in paths.items() if p.exists()}}
            atomic(journal_path, json_bytes(journal))
        from .progress import finish_progress
        finish_progress()
        print("Removing the previous router; preserving settings and verified backups…", flush=True)
        m.change("disable")
        journal["phase"] = "disabled"
        atomic(journal_path, json_bytes(journal))
        archive.mkdir(mode=0o700, exist_ok=True)
        for name in journal["items"]:
            source, destination = paths[name], archive / name
            no_symlink_parents(destination)
            if source.exists() and destination.exists():
                raise RouterError("Migration has conflicting source and archive paths", 4)
            present = source if source.exists() else destination
            if not present.exists() or tree_signature(present) != journal.get("signatures", {}).get(name):
                raise RouterError("Legacy files changed during migration; keep them and request recovery", 4)
            if source.exists():
                source.rename(destination)
            elif not destination.exists():
                raise RouterError("A legacy file disappeared during migration", 4)
        # Adoption is last: reruns finish missing moves before enabling plugin ownership.
        next_state = dict(m.state, installation_backend="plugin", shell_runtime=str(runtime), management_hashes={})
        atomic(state_path, json_bytes(next_state))
        journal["phase"] = "complete"
        atomic(journal_path, json_bytes(journal))
        finish_progress()
        print("Previous program removed. Backups remain at " + str(m.store()), flush=True)
