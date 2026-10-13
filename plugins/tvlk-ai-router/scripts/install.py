"""User-level offline source installer. Never downloads an interpreter."""
import argparse
import hashlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tvlk_ai_router.failed_shell import recognized_failed_shell


def preflight(root):
    user_home = Path.home()
    state_path = user_home / ".local/share/tvlk-ai-router/state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    failed_shell = not state and recognized_failed_shell()
    marker = root / "shell-installation.json"
    owned = not marker.is_symlink() and marker.is_file() and json.loads(marker.read_text()) == {"runtime": str(root), "distribution": "plugin"}
    if not state and state_path.parent.exists():
        remaining = list(state_path.parent.iterdir())
        safe_retry = (owned or failed_shell) and all(p.name == "lock" and not p.is_symlink() and p.is_file() and p.stat().st_size == 0 for p in remaining)
        if remaining and not safe_retry:
            raise ValueError("Router data exists without plugin ownership. Stop before changing its backups or pending transactions.")
    legacy_paths = [user_home / "Applications/TVLK-OpenAI-Router.app", user_home / ".agents/skills/tvlk-ai-router", user_home / ".local/share/tvlk-ai-router-shell/runtime"]
    if state and (state.get("installation_backend") not in (None, "shell", "plugin") or state.get("installation_backend") == "plugin" and state.get("shell_runtime") != str(root)):
        raise ValueError("An unrecognized router installation owns this configuration.")
    if not state and any(p.exists() or p.is_symlink() for p in legacy_paths) and not failed_shell:
        raise ValueError("Legacy router files have no ownership state. Request recovery before setup; no files were removed.")
    marker = root / "shell-installation.json"
    if root.exists() and (not marker.is_file() or json.loads(marker.read_text()).get("runtime") != str(root)):
        raise ValueError("The runtime directory is not owned by this plugin; no files were changed.")
    for path in (root, state_path, *legacy_paths):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Installation paths must not contain symbolic links.")
    if any((root / name).is_symlink() for name in ("shell-installation.json", "src", "src.old", ".venv", "runner.py", "tvlk-ai-router", "manage.sh")) or any(p.is_symlink() for p in (root / "src").rglob("*")):
        raise ValueError("The owned runtime contains symbolic links; stop before updating it.")


def install(package, config=None):
    root = Path.home() / ".local/share/tvlk-ai-router-plugin/runtime"
    preflight(root)
    root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(root.parent / ".installation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another plugin setup is running; retry when it finishes.")
        preflight(root)
        _install(package, root, config)


def _install(package, root, config=None):
    if any(p.is_symlink() for p in (package / "src").rglob("*")):
        raise ValueError("Package source files must not contain symbolic links.")
    wheel = package / "wheels/tomlkit-0.13.3-py3-none-any.whl"
    if not wheel.is_file():
        raise ValueError("The bundled tomlkit wheel is missing. Obtain a complete plugin package.")
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != "c89c649d79ee40629a9fda55f8ace8c6a1b42deb912b2a8fd8d942ddadb606b0":
        raise ValueError("The bundled dependency hash does not match the pinned wheel.")
    print("Preparing the private Python environment…", flush=True)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (root / "shell-installation.json").write_text(json.dumps({"runtime": str(root), "distribution": "plugin"}))
    environment = root / ".venv"
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin/python"
    dependency = subprocess.run([str(python), "-I", "-c", "import tomlkit; assert tomlkit.__version__ == '0.13.3'"], capture_output=True)
    if dependency.returncode:
        if (root / "src").exists():
            raise ValueError("The existing private dependency is unavailable or changed. Stop before updating this runtime.")
        subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", str(wheel)], check=True)
    print("Checking configuration and making a verified backup…", flush=True)
    with tempfile.TemporaryDirectory(prefix=".source-", dir=root) as temporary:
        staged = Path(temporary) / "src"
        shutil.copytree(package / "src", staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
        old_source = root / "src.old"
        if old_source.exists():
            raise ValueError("An unfinished source update exists; stop and inspect the runtime before retrying.")
        had_source = (root / "src").exists()
        wrappers = {name: ((root / name).read_bytes(), (root / name).stat().st_mode & 0o777) for name in ("runner.py", "tvlk-ai-router", "manage.sh") if (root / name).exists()}
        old_moved, new_moved = False, False
        try:
            if had_source:
                (root / "src").rename(old_source)
                old_moved = True
            staged.rename(root / "src")
            new_moved = True
            for name in ("runner.py", "tvlk-ai-router", "manage.sh"):
                shutil.copy2(package / "scripts" / name, root / name)
            (root / "tvlk-ai-router").chmod(0o700)
            subprocess.run([str(python), "-I", str(root / "runner.py"), "shell-install", *(["--config", str(Path(config).resolve())] if config else [])], check=True,
                           env={**os.environ, "TVLK_ROUTER_PROGRESS": "text"})
        except BaseException:
            if new_moved:
                shutil.rmtree(root / "src")
            if old_moved:
                old_source.rename(root / "src")
            for name, (data, mode) in wrappers.items():
                (root / name).write_bytes(data)
                (root / name).chmod(mode)
            raise
        else:
            if old_source.exists():
                shutil.rmtree(old_source)
    print("Installed. Reopen Codex and start a new chat.", flush=True)
    subprocess.run([str(python), "-I", str(root / "runner.py"), "chat", "help"], check=True)


def main():
    parser = argparse.ArgumentParser(description="Set up the plugin runtime; quit Codex/ChatGPT first. Select Python with bash install.sh --python /path/to/python3.")
    parser.add_argument("--config", help="Optional router configuration file")
    args = parser.parse_args()
    try:
        install(Path(__file__).resolve().parents[1], args.config)
        return 0
    except subprocess.CalledProcessError as exc:
        print("Error: Setup stopped (exit " + str(exc.returncode) + "). Read the message above, fix the issue and run install.sh again.", file=sys.stderr)
        return 4
    except (ValueError, OSError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
