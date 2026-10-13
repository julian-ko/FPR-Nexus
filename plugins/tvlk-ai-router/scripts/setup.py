"""Prepare a durable, one-click cold setup without changing live Codex settings."""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


def prepare(package, python):
    home = Path.home()
    state_path = home / ".local/share/tvlk-ai-router/state.json"
    legacy = [home / "Applications/TVLK-OpenAI-Router.app", home / ".agents/skills/tvlk-ai-router",
              home / ".local/share/tvlk-ai-router-shell/runtime"]
    for path in (state_path, *legacy):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Router installation paths must not contain symbolic links")
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    if not state and any(p.exists() for p in legacy):
        raise ValueError("Old router files exist without ownership state. Request recovery before setup.")
    found = (state.get("installation_backend") or "app") if state else "none"
    print("Detected installation: " + found)
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
        "printf 'TVLK-OpenAI-Router setup\\nQuit all Codex / ChatGPT windows and CLI sessions, then press Enter.\\n'\n"
        "read -r ready\n"
        "bash " + shlex.quote(str(target / "package/install.sh")) + " --python " + shlex.quote(str(python)) + "\n"
        "result=$?\n"
        "if [[ $result -eq 0 ]]; then printf '\\nDone. Reopen Codex and start a new chat.\\n'; else printf '\\nSetup stopped. Keep this window and share the error. Run this file again after fixing it.\\n'; fi\n"
        "printf '\\nPress Enter to close.\\n'\nread -r done_read\nexit \"$result\"\n")
    command.chmod(0o700)
    print("Setup file: " + str(command))
    return command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    try:
        command = prepare(Path(__file__).resolve().parents[1], sys.executable)
        if args.open:
            subprocess.run(["/usr/bin/open", "-a", "Terminal", str(command)], check=True)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("Setup could not be prepared: " + str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
