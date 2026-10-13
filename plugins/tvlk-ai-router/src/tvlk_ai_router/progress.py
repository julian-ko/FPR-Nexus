"""Opt-in progress events for the native launcher; stdout stays unchanged."""
import json
import os
import sys
import time


def progress(stage, message, completed=None, total=None, unit=None):
    if os.environ.get("TVLK_ROUTER_PROGRESS") != "1":
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
        self.enabled = os.environ.get("TVLK_ROUTER_PROGRESS") == "1"
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
