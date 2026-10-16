"""CLI entry point. Review retains statistics without changing Codex settings."""
import argparse
import json
import os
import sqlite3
import sys
from importlib.resources import files

from . import __version__
from .config import RouterError
from .manager import Manager
from .progress import finish_progress
from .storage import lock, quiet_check, recover


HELP = """FPR Nexus — Automatic task routing for Codex

Show config     tvlk-ai-router config show
Validate config tvlk-ai-router config validate
Export example  tvlk-ai-router config example > router.toml
Initial setup   tvlk-ai-router install --config ./router.toml
Apply changes   tvlk-ai-router apply
Disable routing tvlk-ai-router disable
Enable routing  tvlk-ai-router enable
List backups    tvlk-ai-router backup list
Restore config  tvlk-ai-router restore <backup-id>
Recover writes  tvlk-ai-router recover
Show help       tvlk-ai-router help
Usage review    tvlk-ai-router review [7d|30d|since-install]
Filter usage    tvlk-ai-router review all --scope nexus --group-by task
Date range      tvlk-ai-router review --from 2026-10-01 --to 2026-10-15 --group-by date
Check updates   tvlk-ai-router update check  (plugin chat launcher)
Prepare update  tvlk-ai-router update prepare  (refresh plugin first)

Every review saves JSON and Markdown tables in ~/.local/share/fpr-nexus-history/exports/.
Use review --json for schema 1.0.0 output. Dates are UTC; reasoning effort is included.
Mutating commands support --dry-run; configuration views support --json.
Restore defaults to configuration only. restore --scope full also rolls back chat history and worktrees.
Enter management commands in Codex chat; the Skill invokes the local program.
Chat changes return a pending request and a Terminal command. Quit Codex/ChatGPT, then run that command.
After changes, reopen Codex and start a new chat. Runtime models still require a real-session check.
"""


def review_options(command):
    command.add_argument("period", nargs="?", default="7d", choices=("7d", "30d", "since-install", "all"))
    command.add_argument("--scope", choices=("all", "nexus"), default="all")
    command.add_argument("--group-by", choices=("date", "model", "task"), default="model")
    command.add_argument("--from", dest="since", help="Inclusive UTC date, YYYY-MM-DD")
    command.add_argument("--to", dest="until", help="Inclusive UTC date, YYYY-MM-DD")
    command.add_argument("--json", action="store_true")


def route_options(command):
    from .routing import TASKS, MODES, REASONS
    command.add_argument("--transcript", required=True)
    command.add_argument("--session-id", required=True)
    command.add_argument("--category", choices=TASKS, required=True)
    command.add_argument("--mode", choices=MODES, required=True)
    command.add_argument("--reason", choices=REASONS, required=True)


def route_record(manager, args):
    from .routing import record_route
    return record_route(manager, args.transcript, args.session_id, args.category, args.mode, args.reason)


def usage_report(manager, args):
    from .history import report
    from .usage_export import dataset, save
    result = dataset(report(manager, args.period, args.scope, args.group_by, args.since, args.until))
    result["exports"] = save(result, manager.data.parent / "fpr-nexus-history" / "exports")
    return result


def parser():
    p = argparse.ArgumentParser(prog="tvlk-ai-router", description=HELP,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version="FPR Nexus " + __version__)
    p.add_argument("--codex-home", help="Target Codex Home; defaults to CODEX_HOME or ~/.codex")
    p.add_argument("--config-dir", help="Unified configuration directory; defaults to ~/.config/tvlk-ai-router")
    p.add_argument("--data-dir", help="State directory; defaults to ~/.local/share/tvlk-ai-router")
    p.add_argument("--agents-home", help="Shared agent configuration directory; defaults to ~/.agents")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("help")
    shell_install = sub.add_parser("shell-install", help=argparse.SUPPRESS)
    shell_install.add_argument("--config")
    shell_install.set_defaults(dry_run=False, json=False)
    review = sub.add_parser("review")
    review_options(review)
    route_options(sub.add_parser("record-route", help="Record a routing choice for the active local turn"))
    for name in ("install", "apply", "disable", "enable", "restore", "recover"):
        c = sub.add_parser(name)
        c.add_argument("--dry-run", action="store_true")
        c.add_argument("--json", action="store_true")
        if name in ("install", "enable"):
            c.add_argument("--config", help="Input configuration; defaults to the bundled example or installed configuration")
        if name == "restore":
            c.add_argument("backup_id")
            c.add_argument("--scope", choices=("config", "full"), default="config")
    c = sub.add_parser("config")
    c.add_argument("operation", choices=("show", "validate", "example"))
    c.add_argument("--config", help="Validate an example file before installation")
    c.add_argument("--json", action="store_true")
    b = sub.add_parser("backup")
    b.add_argument("operation", choices=("list",))
    b.add_argument("--json", action="store_true")
    chat = sub.add_parser("chat", help="Local interface for the chat Skill")
    chat_sub = chat.add_subparsers(dest="operation", required=True)
    for name in ("help", "show", "status", "backups", "cancel"):
        chat_sub.add_parser(name)
    req = chat_sub.add_parser("request")
    review = chat_sub.add_parser("review")
    review_options(review)
    route_options(chat_sub.add_parser("record-route"))
    req.add_argument("action", choices=("apply", "enable", "disable", "restore", "recover"))
    req.add_argument("--backup-id")
    req.add_argument("--scope", choices=("config", "full"), default="config")
    desktop = sub.add_parser("desktop", help=argparse.SUPPRESS)
    ds = desktop.add_subparsers(dest="operation", required=True)
    ds.add_parser("request")
    install = ds.add_parser("install")
    install.add_argument("--source-app", required=True)
    perform = ds.add_parser("perform")
    perform.add_argument("--request-id", required=True)
    return p


def display(value, machine=False):
    finish_progress()
    # JSON contains only the deliberately constructed public report, not raw config.
    if machine:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    if isinstance(value, list):
        for item in value:
            display(item)
    elif isinstance(value, dict):
        labels = {"status": "Status", "runtime": "Runtime routing verification", "baseline": "Pre-install backup",
                  "backup_id": "Backup ID", "pre_restore_backup": "Pre-restore backup",
                  "config_file": "Unified configuration", "backup_directory": "Backup directory",
                  "changes": "Changed paths", "expected": "Expected configuration", "on_disk": "On-disk configuration",
                  "message": "Message", "drift": "Conflicts/drift", "bytes": "Snapshot bytes"}
        for k, v in value.items():
            print(f"{labels.get(k, k)}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}")
    else:
        print(value)


def main(argv=None):
    args = parser().parse_args(argv)
    if not args.command or args.command == "help":
        print(HELP)
        return 0
    if args.command == "config" and args.operation == "example":
        print(files("tvlk_ai_router").joinpath("data/router.example.toml").read_text(), end="")
        return 0
    try:
        if args.command in ("chat", "desktop"):
            from .desktop import dispatch
            result = dispatch(args)
            if args.command == "chat" and args.operation == "review" and not args.json:
                from .review_text import render
                print(render(result))
            else:
                display(result, machine=True)
            return 0
        if args.command == "shell-install" and os.environ.get("TVLK_ROUTER_BACKEND") == "plugin":
            from .migration import migrate
            migrate(os.environ["TVLK_ROUTER_SHELL_ROOT"])
        m = Manager(args.codex_home, args.config_dir, args.data_dir, args.agents_home)
        if args.command == "record-route":
            display(route_record(m, args), machine=True)
            return 0
        if args.command == "review":
            result = usage_report(m, args)
            if args.json:
                display(result, True)
            else:
                from .review_text import render
                print(render(result))
            return 0
        if args.command == "config":
            if args.operation == "show":
                result = m.show()
            else:
                _, d = m.config(args.config)
                result = m.report(d)
            display(result, args.json)
            return 0
        if args.command == "backup":
            display(m.backups(), args.json)
            return 0

        def run():
            if args.command == "shell-install":
                if not os.environ.get("TVLK_ROUTER_SHELL_ROOT"):
                    raise RouterError("Use the isolated Shell installer", 4)
                action = "install" if not m.state else "apply" if m.state["status"] == "enabled" else "enable"
                return m.change(action, args.config)
            if args.command == "restore":
                return m.restore(args.backup_id, args.scope, args.dry_run)
            if args.command == "recover":
                if args.dry_run:
                    return {"pending_transaction": (m.data / "transaction.json").exists(), "dry_run": True}
                return {"recovered": recover(m.data)}
            return m.change(args.command, getattr(args, "config", None), args.dry_run)

        if args.dry_run:
            result = run()
        else:
            quiet_check()
            with lock(m.data):
                if args.command != "recover":
                    recover(m.data)
                # Another CLI may have completed between construction and locking.
                m = Manager(args.codex_home, args.config_dir, args.data_dir, args.agents_home)
                result = run()
        display(result, args.json)
        if args.command == "install" and not args.dry_run and not args.json:
            display(m.show())
            print(HELP)
        return 0
    except RouterError as exc:
        finish_progress()
        print(json.dumps({"error": str(exc), "exit_code": exc.code}, ensure_ascii=False) if getattr(args, "json", False) else "Error: " + str(exc), file=sys.stderr)
        return exc.code
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        finish_progress()
        # Avoid raw tracebacks or configuration contents in ordinary command output.
        print("Error: Cannot safely process local files: " + str(exc), file=sys.stderr)
        return 4
    finally:
        finish_progress()


if __name__ == "__main__":
    sys.exit(main())
