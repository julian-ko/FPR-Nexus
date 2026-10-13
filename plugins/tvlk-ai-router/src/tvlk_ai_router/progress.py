"""Opt-in progress events for the native launcher; stdout stays unchanged."""
import json
import os
import sys
import time


def progress(stage, message, completed=None, total=None, unit=None):
    mode = os.environ.get("TVLK_ROUTER_PROGRESS")
    if mode not in ("1", "text"):
        return
    if mode == "text":
        if total and completed is not None:
            fraction = min(1, completed / total)
            bar = "#" * int(fraction * 20)
            print(f"[{bar:<20}] {fraction:.0%} {message} ({completed}/{total} {unit or ''})", file=sys.stderr, flush=True)
        else:
            print(message, file=sys.stderr, flush=True)
        return
    value = {"stage": stage, "message": message}
    if completed is not None:
        value["completed"] = completed
    if total is not None:
        value["total"] = total
    if unit is not None:
        value["unit"] = unit
    print("TVLK_PROGRESS " + json.dumps(value), file=sys.stderr, flush=True)


class ByteProgress:
    """Actual processed bytes, throttled to ten updates per second."""
    def __init__(self, stage, message, total=None):
        self.stage, self.message, self.total = stage, message, total
        self.completed = 0
        self.enabled = os.environ.get("TVLK_ROUTER_PROGRESS") in ("1", "text")
        self.last = time.monotonic()
        self.emit()

    def emit(self):
        if self.enabled:
            progress(self.stage, self.message, self.completed, self.total, "bytes")

    def advance(self, count):
        self.completed += count
        if self.enabled and time.monotonic() - self.last >= 0.1:
            self.last = time.monotonic()
            self.emit()

    def finish(self):
        self.emit()
