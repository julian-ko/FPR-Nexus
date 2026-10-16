"""Best-effort local collection, detached from interactive hooks."""
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

runtime = Path.home() / ".local/share/tvlk-ai-router-plugin/runtime"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import selected_source


def main():
    sys.path.insert(0, str(selected_source(runtime)))
    from tvlk_ai_router.history import connect, collect
    from tvlk_ai_router.manager import Manager
    state_path = Path.home() / ".local/share/tvlk-ai-router/state.json"
    if state_path.is_symlink() or not state_path.is_file():
        return
    state = json.loads(state_path.read_text())
    targets = state.get("targets", [])
    if len(targets) != 3:
        return
    manager = Manager(targets[0], targets[1], str(state_path.parent), targets[2])
    directory = manager.data.parent / "fpr-nexus-history"
    db = connect(directory)
    try:
        fd = os.open(directory / "collect.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+") as guard:
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            previous = guard.read()
            if "--final" not in sys.argv and previous and time.time() - float(previous) < 300:
                return
            if "--final" not in sys.argv:
                from tvlk_ai_router.updates import check
                policy = check(directory)
                if policy["status"] == "unknown" or policy.get("stale"):
                    check(directory, refresh=True)
            with db:
                collect(db, manager.home, manager.state, datetime.now(timezone.utc))
            guard.seek(0)
            guard.truncate()
            guard.write(str(time.time()))
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Manual review reports errors; background collection must not block a task.
        pass
