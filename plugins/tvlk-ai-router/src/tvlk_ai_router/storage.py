"""Cold snapshots and recoverable multi-file transactions, using only stdlib."""
import contextlib
import fcntl
import json
import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import RouterError, digest, json_bytes
from .progress import progress, ByteProgress
from .processes import running_clients


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]


def absolute(value):
    p = Path(value).expanduser()
    if not p.is_absolute():
        raise RouterError("Use an absolute path or ~/ path: " + str(value))
    return Path(os.path.abspath(p))


def no_symlink_parents(path, include_self=True):
    for item in [*path.parents, *([path] if include_self else [])]:
        if item.is_symlink():
            raise RouterError("Refusing to write through a symbolic link: " + str(item), 4)


def atomic(path, data, mode=0o600):
    no_symlink_parents(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".tvlk-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def copy_chunks(source, destination, on_bytes=None):
    """Stream actual bytes without losing the caller's metadata/safety checks."""
    while chunk := source.read(1024 * 1024):
        destination.write(chunk)
        if on_bytes:
            on_bytes(len(chunk))


def entry(path, blobs=None, on_bytes=None):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"type": "missing"}
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return {"type": "link", "target": os.readlink(path), "mode": mode}
    if stat.S_ISDIR(info.st_mode):
        return {"type": "dir", "mode": mode}
    if not stat.S_ISREG(info.st_mode):
        return {"type": "special"}
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
            if on_bytes:
                on_bytes(len(chunk))
    sha = h.hexdigest()
    result = {"type": "file", "mode": mode, "sha256": sha, "size": info.st_size}
    if blobs is not None:
        destination = blobs / sha
        if not destination.exists():
            with path.open("rb") as source, destination.open("wb") as target:
                copy_chunks(source, target, on_bytes)
            destination.chmod(0o600)
        if entry(destination, on_bytes=on_bytes)["sha256"] != sha:
            raise RouterError("Source changed while copying: " + str(path), 5)
    return result


def inventory(roots, blobs=None, progress_stage=None, byte_total=None):
    roots = unique_roots(roots)
    result = {}
    meter = None
    if progress_stage:
        # A metadata-only pass supplies a real hashing total before reading files.
        # Keep the original traversal below so concurrent directory edits remain
        # visible to the existing before/copy/after snapshot comparisons.
        def size(p):
            try:
                info = p.lstat()
            except FileNotFoundError:
                return 0
            if stat.S_ISREG(info.st_mode):
                return info.st_size
            if stat.S_ISDIR(info.st_mode):
                return sum(size(child) for child in p.iterdir())
            return 0
        if byte_total is None and blobs is None:
            byte_total = sum(size(p) for p in roots)
        meter = ByteProgress(progress_stage, "Processing snapshot bytes", byte_total)
    def walk(p):
        value = entry(p, blobs, meter.advance if meter else None)
        result[str(p)] = value
        if value["type"] == "dir":
            for child in sorted(p.iterdir()):
                walk(child)
    for p in roots:
        walk(p)
    if meter:
        meter.finish()
    return result


def unique_roots(roots):
    result = []
    for path in sorted(set(roots), key=lambda p: (len(p.parts), str(p))):
        if not any(path == x or path.is_relative_to(x) for x in result):
            result.append(path)
    return result


def ensure_outside(store, roots):
    no_symlink_parents(store)
    for root in roots:
        if store == root or store.is_relative_to(root) or root.is_relative_to(store):
            raise RouterError("Backup/state directory overlaps a snapshot root: " + str(root), 4)


def quiet_check(include_router=False):
    """Conservative by design: cannot determine every client's CODEX_HOME."""
    progress("check_apps", "Checking running Codex and ChatGPT processes")
    try:
        blocked = running_clients(include_router)
    except RuntimeError as exc:
        raise RouterError(str(exc), 4) from exc
    if blocked:
        raise RouterError("Quit Codex/ChatGPT desktop and CLI" + (" and the old Router app" if include_router else "") + ", then retry in Terminal. Running processes: " + ", ".join(blocked), 4)


@contextlib.contextmanager
def lock(data_dir):
    no_symlink_parents(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    data_dir.chmod(0o700)
    p = data_dir / "lock"
    no_symlink_parents(p)
    with p.open("a+") as handle:
        os.chmod(p, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RouterError("Another tvlk-ai-router process is changing the configuration", 4) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def snapshot(store, roots, reason, state, home):
    ensure_outside(store, roots)
    progress("inventory", "Inspecting snapshot files")
    before = inventory(roots, progress_stage="inventory")
    size = sum(e.get("size", 0) for e in before.values())
    ancestor = store
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < size * 2 + 8 * 1024 * 1024:
        raise RouterError("Insufficient disk space: backup and transaction staging require at least twice the source size", 4)
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    store.chmod(0o700)
    ident = stamp()
    partial = store / (ident + ".partial")
    partial.mkdir(mode=0o700)
    blobs = partial / "files"
    blobs.mkdir(mode=0o700)
    # Each source and corresponding blob is hashed; duplicate content is copied
    # only once. Count all three types of actual I/O rather than file completions.
    unique_sizes = {e["sha256"]: e["size"] for e in before.values() if e["type"] == "file"}
    copy_bytes = size * 2 + sum(unique_sizes.values())
    copied = inventory(roots, blobs, progress_stage="snapshot_copy", byte_total=copy_bytes)
    after = inventory(roots, progress_stage="snapshot_verification", byte_total=size)
    if before != copied or before != after:
        raise RouterError("Source changed during backup; the unfinished snapshot remains as .partial and configuration was not written", 5)
    manifest = {"schema": 1, "id": ident, "reason": reason, "codex_home": str(home),
                "roots": list(map(str, roots)), "entries": copied, "router_state": state,
                "bytes": size, "created_at": datetime.now(timezone.utc).isoformat()}
    raw = json_bytes(manifest)
    atomic(partial / "manifest.json", raw)
    atomic(partial / "COMPLETE", (digest(raw) + "\n").encode())
    for item in blobs.iterdir():
        item.chmod(0o400)
    blobs.chmod(0o500)
    (partial / "manifest.json").chmod(0o400)
    (partial / "COMPLETE").chmod(0o400)
    partial.chmod(0o500)
    destination = store / ident
    os.rename(partial, destination)
    load_snapshot(store, ident, verify=True, progress_stage="backup_verification")
    return manifest


def load_snapshot(store, ident, verify=True, progress_stage=None):
    import re
    if not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", ident):
        raise RouterError("Invalid backup-id")
    p = store / ident
    no_symlink_parents(p)
    try:
        raw = (p / "manifest.json").read_bytes()
        if (p / "COMPLETE").read_text().strip() != digest(raw):
            raise RouterError("Backup manifest verification failed", 5)
        m = json.loads(raw)
        if m["schema"] != 1 or m["id"] != ident:
            raise RouterError("Backup schema or ID does not match", 5)
        roots = [absolute(r) for r in m["roots"]]
        meter = ByteProgress(progress_stage, "Verifying backup bytes",
                             sum(e.get("size", 0) for e in m["entries"].values())) if progress_stage and verify else None
        for name, value in m["entries"].items():
            path = absolute(name)
            if not any(path == r or path.is_relative_to(r) for r in roots):
                raise RouterError("Backup manifest contains a path outside its roots", 5)
            if value["type"] == "file":
                sha = value["sha256"]
                if not re.fullmatch(r"[a-f0-9]{64}", sha):
                    raise RouterError("Invalid file hash", 5)
                if verify and entry(p / "files" / sha, on_bytes=meter.advance if meter else None).get("sha256") != sha:
                    raise RouterError("Damaged backup file: " + name, 5)
        if meter:
            meter.finish()
        return m
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RouterError("Backup is incomplete or unreadable: " + ident, 5) from exc


def materialize(path, value, blobs, on_bytes=None):
    no_symlink_parents(path, include_self=False)
    kind = value["type"]
    if kind == "missing":
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    elif kind == "dir":
        no_symlink_parents(path)
        path.mkdir(mode=value["mode"], parents=False, exist_ok=True)
        path.chmod(value["mode"])
    elif kind == "link":
        temporary = path.parent / (".tvlk-link-" + uuid.uuid4().hex)
        try:
            os.symlink(value["target"], temporary)
            os.replace(temporary, path)
        finally:
            if temporary.is_symlink():
                temporary.unlink()
    elif kind == "file":
        no_symlink_parents(path)
        source = blobs / value["sha256"]
        if entry(source, on_bytes=on_bytes).get("sha256") != value["sha256"]:
            raise RouterError("Transaction content verification failed", 6)
        # Stream large snapshots; never read entire worktrees into RAM.
        fd, temporary = tempfile.mkstemp(prefix=".tvlk-", dir=path.parent)
        try:
            with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
                copy_chunks(src, dst, on_bytes)
                dst.flush()
                os.fsync(dst.fileno())
                os.fchmod(dst.fileno(), value["mode"])
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    else:
        raise RouterError("Cannot restore a special file: " + str(path), 4)


def recover(data_dir):
    journal = data_dir / "transaction.json"
    if not journal.exists():
        return False
    tx = json.loads(journal.read_bytes())
    if tx.get("status") == "committed":
        journal.unlink()
        return True
    blobs = data_dir / "transaction-files"
    # Check *all* targets before rollback, not halfway through the operation.
    allowed = {}
    for op in tx["ops"]:
        allowed.setdefault(op["path"], []).extend((op["before"], op["after"]))
    for name, values in allowed.items():
        if entry(Path(name)) not in values:
            raise RouterError("Unfinished transaction conflicts with user changes: " + name, 6)
    for op in reversed(tx["ops"]):
        path = Path(op["path"])
        if entry(path) == op["after"] and op["before"] != op["after"]:
            materialize(path, op["before"], blobs)
    journal.unlink()
    return True


def transact(data_dir, edits, expected=None, fail_after=None):
    """edits: Path -> bytes, None (delete), or (metadata, immutable blob dir)."""
    if (data_dir / "transaction.json").exists():
        raise RouterError("An unfinished transaction exists; run tvlk-ai-router recover first", 6)
    blobs = data_dir / "transaction-files"
    if blobs.exists():
        shutil.rmtree(blobs)
    blobs.mkdir(mode=0o700)
    ops = []
    preparation = ByteProgress("prepare_transaction", "Preparing safe transaction files")
    expanded = dict(edits)
    for path, value in list(edits.items()):
        if value is not None:
            for parent in reversed(path.parents):
                if not parent.exists() and parent not in expanded:
                    expanded[parent] = ({"type": "dir", "mode": 0o700}, None)
    for path, value in expanded.items():
        no_symlink_parents(path, include_self=False)
        before = entry(path, blobs, preparation.advance)
        if expected is not None and str(path) in expected and before != expected[str(path)]:
            raise RouterError("Configuration changed before writing: " + str(path), 4)
        if value is None:
            after = {"type": "missing"}
        elif isinstance(value, bytes):
            sha = digest(value)
            atomic(blobs / sha, value)
            after = {"type": "file", "mode": before.get("mode", 0o600), "sha256": sha, "size": len(value)}
        else:
            after, source_blobs = value
            if after["type"] == "file":
                target = blobs / after["sha256"]
                if not target.exists():
                    with (source_blobs / after["sha256"]).open("rb") as src, target.open("wb") as dst:
                        copy_chunks(src, dst, preparation.advance)
                    target.chmod(0o600)
        if before == after:
            continue
        if before["type"] not in ("missing", after["type"]) and after["type"] != "missing":
            raise RouterError("Refusing to change the file type automatically: " + str(path), 4)
        ops.append({"path": str(path), "before": before, "after": after})
    # Read-only configuration directories need temporary owner write access.
    # Keep both permission changes in the journal and finalize permissions last.
    by_path = {op["path"]: op for op in ops}
    parents = {str(p) for op in ops for p in Path(op["path"]).parents}
    extra = []
    for name in sorted(parents, key=lambda x: len(Path(x).parts)):
        op = by_path.get(name)
        before = op["before"] if op else entry(Path(name))
        if op and op["after"]["type"] == "dir" and before["type"] == "missing":
            desired = dict(op["after"])
            op["after"] = dict(desired, mode=desired["mode"] | 0o700)
            if desired != op["after"]:
                extra.append({"path": name, "before": op["after"], "after": desired, "phase": 3})
        elif before["type"] == "dir" and before["mode"] & 0o700 != 0o700:
            temporary = dict(before, mode=before["mode"] | 0o700)
            extra.append({"path": name, "before": before, "after": temporary, "phase": 0})
            if op:
                op["before"] = temporary
                if op["after"]["type"] == "dir":
                    op["phase"] = 3
            else:
                extra.append({"path": name, "before": temporary, "after": before, "phase": 3})
    ops += extra
    def order(op):
        depth = len(Path(op["path"]).parts)
        if "phase" in op:
            return (op["phase"], -depth if op["phase"] == 3 else depth)
        if op["after"]["type"] == "dir":
            return (0, depth) if op["before"]["type"] == "missing" else (3, -depth)
        if op["after"]["type"] == "missing":
            return (2, -depth)
        return (1, depth)
    preparation.finish()
    ops.sort(key=order)
    tx = {"schema": 1, "status": "pending", "ops": ops}
    journal = data_dir / "transaction.json"
    atomic(journal, json_bytes(tx))
    work = sum(op["before"].get("size", 0) + 3 * op["after"].get("size", 0) for op in ops)
    applied = ByteProgress("apply_transaction", "Applying and verifying configuration bytes", work)
    try:
        for i, op in enumerate(ops):
            path = Path(op["path"])
            if entry(path, on_bytes=applied.advance) != op["before"]:
                raise RouterError("File changed during the transaction: " + str(path), 6)
            materialize(path, op["after"], blobs, applied.advance)
            if entry(path, on_bytes=applied.advance) != op["after"]:
                raise RouterError("Post-write verification failed: " + str(path), 6)
            if fail_after is not None and i == fail_after:
                raise OSError("injected write failure")
        applied.finish()
        progress("final_verification", "All configuration changes passed post-write verification", len(ops), len(ops), "files")
        tx["status"] = "committed"
        atomic(journal, json_bytes(tx))
        journal.unlink()
        shutil.rmtree(blobs)
    except Exception as exc:
        try:
            recover(data_dir)
        except Exception as rollback:
            raise RouterError("Transaction failed and rollback is blocked; the journal was preserved. Run recover: " + str(rollback), 6) from exc
        raise RouterError("Transaction failed and was rolled back: " + str(exc), 6) from exc
