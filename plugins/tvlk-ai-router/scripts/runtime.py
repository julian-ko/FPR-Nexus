"""Versioned runtime activation. Does not write Codex configuration or usage data."""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

PROTOCOL = 1


def safe(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Runtime paths must not contain symbolic links: " + str(path))
    return path


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Invalid runtime version")
    return tuple(map(int, value.split(".")))


def read(path):
    return json.loads(safe(path).read_text())


def atomic(path, value):
    safe(path)
    fd, temporary = tempfile.mkstemp(prefix=".runtime-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fingerprint(directory):
    safe(directory)
    entries = {}
    for path in sorted(directory.rglob("*")):
        safe(path)
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("Runtime contains a non-regular file")
        entries[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


@contextlib.contextmanager
def locked(root):
    safe(root)
    safe(root.parent / ".installation.lock")
    root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(root.parent / ".installation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def release(root, record):
    version(record["version"])
    directory = safe(root / "releases" / record["version"])
    metadata = read(directory / "ready.json")
    if metadata != {"version": record["version"], "digest": record["digest"]}:
        raise ValueError("Runtime release metadata changed")
    payload = directory / "payload"
    if fingerprint(payload) != record["digest"]:
        raise ValueError("Runtime release files changed; use recovery")
    if read(payload / "runtime.json")["protocol"] != PROTOCOL:
        raise ValueError("Runtime launcher upgrade requires setup")
    return payload


@contextlib.contextmanager
def configuration_lock(root):
    directory = root.parent.parent / "tvlk-ai-router"
    state = read(directory / "state.json")
    if state.get("installation_backend") != "plugin" or state.get("shell_runtime") != str(root):
        raise ValueError("Configuration ownership requires recovery before update")
    if safe(directory / "transaction.json").exists():
        raise ValueError("Finish the pending configuration recovery before updating")
    path = safe(directory / "lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def active(root):
    if read(root / "shell-installation.json") != {"runtime": str(root), "distribution": "plugin"}:
        raise ValueError("Runtime ownership could not be verified")
    state = read(root / "active.json")
    if state.get("schema") != 1:
        raise ValueError("Unsupported runtime activation state")
    release(root, state["current"])
    return state


def selected_source(root):
    return release(root, active(root)["current"]) / "src"


def stage(package, root):
    number = read(package / "plugin.json")["version"]
    version(number)
    contract = read(package / "runtime.json")
    if contract["protocol"] != PROTOCOL:
        raise ValueError("Runtime launcher upgrade requires setup")
    safe(root / "releases")
    (root / "releases").mkdir(mode=0o700, exist_ok=True)
    target = safe(root / "releases" / number)
    before = fingerprint(package / "src")
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=root / "releases") as temporary:
        staged = Path(temporary)
        payload = staged / "payload"
        payload.mkdir(mode=0o700)
        shutil.copytree(package / "src", payload / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (payload / "runtime.json").write_text(json.dumps(contract, sort_keys=True))
        if before != fingerprint(payload / "src") or before != fingerprint(package / "src"):
            raise ValueError("Package changed while preparing update")
        record = {"version": number, "digest": fingerprint(payload)}
        (staged / "ready.json").write_text(json.dumps(record))
        if target.exists():
            release(root, record)
        else:
            staged.rename(target)
            staged.mkdir()  # TemporaryDirectory only cleans its own empty staging path.
    return record


def probe(root, payload):
    code = '''import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
os.environ['TVLK_ROUTER_SHELL_ROOT'] = sys.argv[2]
os.environ['TVLK_ROUTER_BACKEND'] = 'plugin'
import tomlkit
assert tomlkit.__version__ == '0.13.3'
from tvlk_ai_router import __version__
from tvlk_ai_router.desktop import desktop_manager
from tvlk_ai_router.config import desired_keys, native_agents, digest, parse
from tvlk_ai_router.usage_export import dataset
from tvlk_ai_router.cli import parser
m = desktop_manager()
if not m.state or m.state.get('installation_backend') != 'plugin':
    raise ValueError('Initial setup or legacy migration is required')
if m.drift():
    raise ValueError('Managed configuration was edited; recovery is required')
raw = m.source.read_bytes() if m.source.exists() else None
if raw is None and m.state.get('applied_config_bytes'):
    import base64
    raw = base64.b64decode(m.state['applied_config_bytes'])
d = parse(raw) if raw is not None else None
print(json.dumps({'version': __version__, 'compatible': {
 'config': digest(raw) if raw is not None else None, 'state': digest(m.state_file.read_bytes()),
 'keys': desired_keys(d) if d else None, 'agents': {k: digest(v) for k,v in native_agents(d).items()} if d else None}}, sort_keys=True))
'''
    result = subprocess.run([str(root / ".venv/bin/python"), "-I", "-c", code, str(payload / "src"), str(root)],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError("Runtime validation failed; existing version preserved. " + result.stderr[-800:])
    value = json.loads(result.stdout)
    version(value["version"])
    return value


def initialize(package, root):
    record = stage(package, root)
    previous = active(root)["current"] if (root / "active.json").exists() else None
    checked = probe(root, release(root, record))
    if checked["version"] != record["version"]:
        raise ValueError("Package and runtime versions differ")
    if record == previous:
        return
    atomic(root / "active.json", {"schema": 1, "current": record, "previous": previous, "hold": None})


def sync(package, root, automatic=True, rollback=False):
    if not (safe(root) / "active.json").exists():
        return {"status": "maintenance_required", "reason": "Initial setup or one-time upgrade from the old runtime is required"}
    try:
        with locked(root), configuration_lock(root):
            state = active(root)
            current = state["current"]
            if rollback:
                candidate = state.get("previous")
                if not candidate:
                    return {"status": "unavailable", "reason": "No previous runtime version"}
            else:
                number = read(package / "plugin.json")["version"]
                if version(number) <= version(current["version"]):
                    return {"status": "current", "version": current["version"]}
                if automatic and state.get("hold") and version(number) <= version(state["hold"]):
                    return {"status": "held", "version": current["version"], "reason": "Previous update was rolled back"}
                candidate_contract = read(package / "runtime.json")
                if candidate_contract != read(release(root, current) / "runtime.json"):
                    return {"status": "maintenance_required", "reason": "Runtime, dependency or data contract changed"}
                candidate = stage(package, root)
            old_payload, new_payload = release(root, current), release(root, candidate)
            if read(old_payload / "runtime.json") != read(new_payload / "runtime.json"):
                return {"status": "maintenance_required", "reason": "Rollback needs configuration or data recovery"}
            old, new = probe(root, old_payload), probe(root, new_payload)
            if new["version"] != candidate["version"]:
                raise ValueError("Package and runtime versions differ")
            if old["compatible"] != new["compatible"]:
                return {"status": "maintenance_required", "reason": "Native settings changed; use setup with clients closed"}
            if probe(root, old_payload)["compatible"] != old["compatible"]:
                raise ValueError("Configuration changed during validation; retry")
            atomic(root / "active.json", {"schema": 1, "current": candidate, "previous": current,
                                         "hold": current["version"] if rollback else None})
            return {"status": "rolled_back" if rollback else "updated", "version": candidate["version"], "restart_required": False}
    except BlockingIOError:
        return {"status": "busy", "reason": "Another setup or update is running; existing runtime remains available"}


def main():
    root = Path.home() / ".local/share/tvlk-ai-router-plugin/runtime"
    try:
        result = sync(Path(__file__).resolve().parents[1], root)
        print(json.dumps(result))
        if result["status"] == "maintenance_required":
            print(result["reason"], file=sys.stderr)
        return 4 if result["status"] == "maintenance_required" else 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("Runtime update stopped: " + str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
