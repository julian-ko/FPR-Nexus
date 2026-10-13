"""Prepare a durable, one-click cold setup without changing live Codex settings."""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

# This detector uses only stdlib, so waiting does not require the private environment.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tvlk_ai_router.processes import running_clients
from tvlk_ai_router.failed_shell import recognized_failed_shell


def wait_for_clients():
    print("Setup is ready. Quit Codex / ChatGPT, CLI sessions and the old Router app.", flush=True)
    print("Keep this window open. Setup continues automatically after they exit. Press Ctrl+C to cancel.", flush=True)
    previous = None
    clear_checks = 0
    while clear_checks < 2:
        blocked = running_clients(include_router=True)
        if blocked:
            clear_checks = 0
            if blocked != previous:
                print("Waiting for clients to exit: " + ", ".join(blocked), flush=True)
        else:
            clear_checks += 1
        previous = blocked
        if clear_checks < 2:
            time.sleep(2)
    print("Clients have exited. Continuing setup automatically…", flush=True)


def run_install(package):
    wait_for_clients()
    # The installer retains its own cold-client check before configuration writes.
    return subprocess.run([sys.executable, "-I", str(package / "scripts/install.py")]).returncode


def prepare(package, python):
    home = Path.home()
    state_path = home / ".local/share/tvlk-ai-router/state.json"
    legacy = [home / "Applications/TVLK-OpenAI-Router.app", home / ".agents/skills/tvlk-ai-router",
              home / ".local/share/tvlk-ai-router-shell/runtime"]
    for path in (state_path, *legacy):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Router installation paths must not contain symbolic links")
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    failed_shell = not state and recognized_failed_shell()
    if not state and any(p.exists() for p in legacy) and not failed_shell:
        raise ValueError("Old router files exist without ownership state. Request recovery before setup.")
    found = (state.get("installation_backend") or "app") if state else "none"
    print("Detected installation: " + found)
    if failed_shell:
        print("Detected an incomplete Shell setup. Its files will be archived after clients exit; setup will then continue.")
    if found in ("app", "shell"):
        print("Setup will verify backups, remove the old program and Skill, and keep your settings.")
    parent = home / ".local/share/tvlk-ai-router-plugin/setup"
    if any(p.is_symlink() for p in (parent, *parent.parents)):
        raise ValueError("Setup paths must not contain symbolic links")
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    target = parent / uuid.uuid4().hex
    shutil.copytree(package, target / "package", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "tests"))
    target.chmod(0o700)
    command = target / "Setup-Router.command"
    inherited_home = os.environ.get("CODEX_HOME", str(home / ".codex"))
    command.write_text("#!/bin/bash\nset -u\nexport CODEX_HOME=" + shlex.quote(inherited_home) + "\n"
        + shlex.quote(str(python)) + " -I " + shlex.quote(str(target / "package/scripts/setup.py")) + " --install\n"
        "result=$?\n"
        "if [[ $result -eq 0 ]]; then printf '\\nDone. Reopen Codex and start a new chat.\\n'; elif [[ $result -eq 130 ]]; then printf '\\nSetup cancelled. Run this file again when ready.\\n'; else printf '\\nSetup stopped. Keep this window and share the error. Run this file again after fixing it.\\n'; fi\n"
        "printf '\\nPress Enter to close.\\n'\nread -r done_read\nexit \"$result\"\n")
    command.chmod(0o700)
    print("Setup file: " + str(command))
    return command


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--open", action="store_true")
    mode.add_argument("--install", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.install:
            return run_install(Path(__file__).resolve().parents[1])
        command = prepare(Path(__file__).resolve().parents[1], sys.executable)
        if args.open:
            subprocess.run(["/usr/bin/open", "-a", "Terminal", str(command)], check=True)
        return 0
    except KeyboardInterrupt:
        print("Setup cancelled.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Setup could not be prepared: " + str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
