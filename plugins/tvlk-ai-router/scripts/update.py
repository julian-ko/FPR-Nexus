"""Check policy or open setup from the already-refreshed host plugin."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

package = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(package / "scripts"))
from runtime import active, sync
sys.path.insert(0, str(package / "src"))
from tvlk_ai_router import __version__
from tvlk_ai_router.updates import check, version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "prepare", "rollback"), nargs="?", default="check")
    args = parser.parse_args()
    root = Path.home() / ".local/share/tvlk-ai-router-plugin/runtime"
    if args.action == "rollback":
        result = sync(package, root, automatic=False, rollback=True)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "rolled_back" else 4
    result = check(refresh=True)
    result["package_version"] = __version__
    if (root / "active.json").exists():
        state = active(root)
        result["activation"] = state
        from tvlk_ai_router.updates import check as runtime_check
        result["runtime"] = runtime_check(current=state["current"]["version"])
    runtime = Path.home() / ".local/share/tvlk-ai-router-plugin/runtime/src/tvlk_ai_router/__init__.py"
    if "runtime" not in result and runtime.is_file() and not runtime.is_symlink():
        import re
        match = re.search(r'__version__ = "([0-9.]+)"', runtime.read_text())
        if match:
            from tvlk_ai_router.updates import check as runtime_check
            result["runtime"] = runtime_check(current=match[1])
    print(json.dumps(result, indent=2), flush=True)
    if args.action == "check":
        return 0
    if result["status"] == "unknown" or result.get("fetch_error"):
        print("Cannot prepare an update without a fresh version policy. Retry, or use setup for an explicitly selected local package.", file=sys.stderr)
        return 4
    if version(__version__) < version(result["latest"]):
        print("Refresh FPR Nexus in Codex first. This plugin package is older than the latest release; no runtime files changed.", file=sys.stderr)
        return 4
    if result.get("runtime") and version(result["runtime"]["installed_version"]) > version(__version__):
        print("The runtime is newer than this plugin package. Refresh the host plugin; automatic downgrade is not allowed.", file=sys.stderr)
        return 4
    result = sync(package, root, automatic=False)
    print(json.dumps(result, indent=2))
    if result["status"] in ("updated", "current"):
        return 0
    if result["status"] != "maintenance_required":
        return 4
    return subprocess.run([sys.executable, "-I", str(package / "scripts/setup.py"), "--open"]).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print("Update check failed: " + str(exc), file=sys.stderr)
        sys.exit(4)
