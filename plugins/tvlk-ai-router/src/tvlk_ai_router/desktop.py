"""Native-app installation and explicit chat-to-desktop handoff. No daemon."""
import json
import os
import plistlib
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import RouterError, json_bytes
from .manager import Manager, read
from .progress import progress, ByteProgress
from .storage import atomic, entry, lock, no_symlink_parents, quiet_check, recover, copy_chunks

APP_NAME = "TVLK-OpenAI-Router.app"
BUNDLE_ID = "com.traveloka.tvlk-openai-router"
ACTIONS = {"apply", "enable", "disable", "restore", "recover"}
CHAT_HELP = {
    "title": "FPR Nexus · Chat management",
    "usage": "Enter these commands in local Codex chat, or use $tvlk-ai-router help explicitly. No terminal is needed.",
    "commands": ["tvlk-ai-router help", "tvlk-ai-router config show", "tvlk-ai-router status",
                 "tvlk-ai-router backup list", "tvlk-ai-router disable", "tvlk-ai-router enable",
                 "tvlk-ai-router apply", "tvlk-ai-router restore <backup-id>",
                 "tvlk-ai-router review", "tvlk-ai-router review 30d", "tvlk-ai-router review since-install",
                 "tvlk-ai-router review all --scope nexus --group-by task",
                 "tvlk-ai-router review --from 2026-10-01 --to 2026-10-15 --group-by date",
                 "tvlk-ai-router update check", "tvlk-ai-router update prepare"],
    "changes": "Change requests open the local management window. Quit Codex, then click Run. Pending means the change has not been applied.",
    "scope": "Requires Codex chat with local tool access. Ordinary ChatGPT cloud chats cannot control local models or configuration.",
}


def installed_app():
    return Path.home() / "Applications" / APP_NAME


def desktop_manager():
    data = Path.home() / ".local/share/tvlk-ai-router"
    state = data / "state.json"
    if state.exists():
        value = json.loads(read(state))
        targets = value.get("targets", [])
        if len(targets) != 3:
            raise RouterError("Installed state is missing target paths; stopped to avoid changing the wrong instance", 4)
        return Manager(targets[0], targets[1], str(data), targets[2])
    return Manager()


def refreshed(m):
    return Manager(str(m.home), str(m.config_dir), str(m.data), str(m.shared))


def request_file(m):
    return m.data / "chat-request.json"


def request_status(m):
    path = request_file(m)
    if not path.exists():
        return {"status": "none", "message": "No pending management request"}
    value = json.loads(read(path))
    if not re.fullmatch(r"[a-f0-9]{32}", value.get("id", "")) or value.get("action") not in ACTIONS:
        raise RouterError("Unsupported management request format", 4)
    return value


def verify_app(app):
    no_symlink_parents(app)
    try:
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    except (OSError, ValueError) as exc:
        raise RouterError("Not a valid TVLK installer application", 4) from exc
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise RouterError("The existing app is not TVLK-OpenAI-Router; refusing to overwrite", 4)
    result = subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], capture_output=True)
    if result.returncode:
        raise RouterError("Application signature integrity check failed; obtain a complete installer package", 4)


def bootstrap(source_app, m=None):
    """Called by the GUI after its Install button. Never called merely on import."""
    source = Path(source_app).resolve()
    progress("preflight", "Verifying the installer application")
    verify_app(source)
    quiet_check()
    m = m or desktop_manager()
    destination = installed_app()
    no_symlink_parents(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    same = source == destination.resolve()
    old = destination.with_name(".tvlk-router-old-" + uuid.uuid4().hex + ".app")
    staging = destination.with_name(".tvlk-router-new-" + uuid.uuid4().hex + ".app")
    moved_old = copied_new = committed = False
    try:
        if not same:
            if destination.exists():
                verify_app(destination)
            total = sum(path.stat().st_size for path in source.rglob("*") if path.is_file() and not path.is_symlink())
            copied = ByteProgress("copy_app", "Copying application bytes", total)
            def copy_file(src, dst):
                with open(src, "rb") as source_file, open(dst, "wb") as target_file:
                    copy_chunks(source_file, target_file, copied.advance)
                shutil.copystat(src, dst)
                return dst
            shutil.copytree(source, staging, symlinks=True, copy_function=copy_file)
            copied.finish()
            progress("verify_app", "Verifying the copied application")
            verify_app(staging)
        with lock(m.data):
            recover(m.data)
            m = refreshed(m)
            if not same:
                if destination.exists():
                    os.replace(destination, old)
                    moved_old = True
                os.replace(staging, destination)
                copied_new = True
            action = "install" if not m.state else "apply" if m.state["status"] == "enabled" else "enable"
            result = m.change(action, migrate_english=True)
            committed = True
        # Cleanup is deliberately outside the configuration commit boundary.
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)
        defaults = m.show().get("expected")
        progress("complete", "Installation completed")
        return {"status": "installed", "application": str(destination), "configuration": result,
                "defaults": defaults, "help": CHAT_HELP,
                "next": "Reopen Codex and start a new chat. Enter tvlk-ai-router help."}
    except Exception:
        if copied_new and not committed:
            shutil.rmtree(destination)
        if moved_old and not committed:
            os.replace(old, destination)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def queue_request(m, action, backup_id=None, scope="config"):
    if action not in ACTIONS or scope not in ("config", "full"):
        raise RouterError("Unsupported chat management action")
    if action in ("apply", "enable"):
        from .updates import require_supported
        try:
            require_supported(m.data.parent / "fpr-nexus-history")
        except ValueError as exc:
            raise RouterError(str(exc), 4) from exc
    if action == "restore":
        if not backup_id:
            raise RouterError("Restore requires an explicit backup-id; list backups first")
        from .storage import load_snapshot
        load_snapshot(m.store(), backup_id)
    elif backup_id is not None or scope != "config":
        raise RouterError("backup-id and scope are only valid for restore")
    app = installed_app()
    shell_root = os.environ.get("TVLK_ROUTER_SHELL_ROOT")
    if not shell_root and not app.exists():
        raise RouterError("The local management app is not installed; double-click the installer", 4)
    if not shell_root:
        verify_app(app)
    with lock(m.data):
        m = refreshed(m)
        if not m.state:
            raise RouterError("Routing is not configured; use the installer first", 4)
        existing = request_status(m)
        if existing["status"] in ("pending", "running"):
            raise RouterError("A request is already pending; complete or cancel it before submitting another", 4)
        value = {"schema": 1, "id": uuid.uuid4().hex, "action": action, "backup_id": backup_id,
                 "scope": scope, "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
                 "targets": list(map(str, (m.home, m.config_dir, m.shared))),
                 "state_before": entry(m.state_file), "config_before": entry(m.source)}
        atomic(request_file(m), json_bytes(value))
    if shell_root:
        import shlex
        command = "bash " + shlex.quote(str(Path(shell_root) / "manage.sh")) + " " + value["id"]
        return {"status": "pending", "id": value["id"], "action": action, "command": command,
                "message": "Configuration has not changed. Quit Codex/ChatGPT, then run the command in Terminal."}
    try:
        subprocess.run(["/usr/bin/open", "-n", str(app), "--args", "--request", value["id"]],
                       check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        with lock(m.data):
            value.update(status="failed", error="Cannot open the local management window; submit the request again")
            atomic(request_file(m), json_bytes(value))
        raise RouterError(value["error"], 4) from exc
    return {"status": "pending", "id": value["id"], "action": action,
            "message": "The local management window is open. Quit Codex/ChatGPT, then click Run. Configuration has not changed yet."}


def cancel_request(m):
    with lock(m.data):
        value = request_status(m)
        if value["status"] not in ("pending", "failed"):
            return {"status": value["status"], "message": "No pending request can be cancelled"}
        value["status"] = "cancelled"
        atomic(request_file(m), json_bytes(value))
        return {"status": "cancelled", "id": value["id"]}


def perform_request(m, ident):
    progress("preflight", "Validating the management request")
    quiet_check()
    with lock(m.data):
        recover(m.data)
        m = refreshed(m)
        value = request_status(m)
        if value.get("id") != ident:
            raise RouterError("The request expired or was replaced; submit it again in chat", 4)
        if value["status"] == "cancelled":
            raise RouterError("The request was cancelled", 4)
        if value["status"] == "completed":
            return value
        if m.state and m.state.get("last_request_id") == ident:
            value.update(status="completed", result={"message": "The configuration transaction was committed; completion status was recovered"})
            atomic(request_file(m), json_bytes(value))
            progress("complete", "Management request completed")
            return value
        if value["targets"] != list(map(str, (m.home, m.config_dir, m.shared))):
            raise RouterError("Request targets do not match the installed instance", 4)
        if entry(m.state_file) != value["state_before"] or entry(m.source) != value["config_before"]:
            raise RouterError("Configuration changed after submission; cancel and submit the request again", 4)
        value["status"] = "running"
        atomic(request_file(m), json_bytes(value))
        try:
            m.operation_request_id = ident
            action = value["action"]
            if action == "restore":
                result = m.restore(value["backup_id"], value["scope"])
            elif action == "recover":
                result = {"recovered": True}
            else:
                result = m.change(action)
            value.update(status="completed", result=result)
            atomic(request_file(m), json_bytes(value))
            progress("complete", "Management request completed")
            return value
        except Exception as exc:
            value.update(status="failed", error=str(exc))
            atomic(request_file(m), json_bytes(value))
            raise


def dispatch(args):
    if os.environ.get("TVLK_ROUTER_SHELL_ROOT"):
        CHAT_HELP["title"] = "FPR Nexus · Plugin chat management"
        CHAT_HELP["usage"] = "Read-only commands run in local Codex chat. Changes require a Terminal command after quitting Codex."
        CHAT_HELP["changes"] = "A change returns a quoted bash manage.sh command. Quit Codex/ChatGPT, then run it in Terminal. Pending means no configuration change has been applied."
        CHAT_HELP["setup"] = "Enter tvlk-ai-router setup to open the setup window. It checks and migrates old installations before applying plugin settings."
    if os.environ.get("TVLK_ROUTER_SHELL_ROOT") and args.command == "desktop" and args.operation == "install":
        raise RouterError("Use bash install.sh for the source package", 4)
    if args.command == "chat" and args.operation == "help":
        return CHAT_HELP
    m = desktop_manager()
    if args.command == "desktop":
        if args.operation == "install":
            return bootstrap(args.source_app, m)
        if args.operation == "perform":
            return perform_request(m, args.request_id)
        return request_status(m)
    if args.operation == "help":
        return CHAT_HELP
    if args.operation == "show":
        return m.show()
    if args.operation == "review":
        from .cli import usage_report
        return usage_report(m, args)
    if args.operation == "status":
        from .updates import check
        return {**m.show(), "pending_request": request_status(m), "version_policy": check(m.data.parent / "fpr-nexus-history")}
    if args.operation == "backups":
        return m.backups()
    if args.operation == "cancel":
        return cancel_request(m)
    return queue_request(m, args.action, args.backup_id, args.scope)
