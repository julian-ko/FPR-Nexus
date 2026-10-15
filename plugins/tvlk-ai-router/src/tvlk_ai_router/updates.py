"""Version policy only: no usage upload, remote commands, or package execution."""
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from . import __version__

POLICY_URL = "https://raw.githubusercontent.com/julian-ko/FPR-Nexus/main/releases/policy.json"
REPOSITORY = "https://github.com/julian-ko/FPR-Nexus"


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Versions must use major.minor.patch")
    return tuple(map(int, value.split(".")))


def instant(value):
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not at.tzinfo:
        raise ValueError("Version policy timestamps require a timezone")
    return at.astimezone(timezone.utc)


def validate(policy):
    if not isinstance(policy, dict) or policy.get("schema") != 1:
        raise ValueError("Unsupported version policy")
    if version(policy.get("minimum_supported")) > version(policy.get("latest")):
        raise ValueError("Minimum version exceeds latest")
    if policy.get("upgrade_deadline") is not None:
        instant(policy["upgrade_deadline"])
    instant(policy["published_at"])
    return {k: policy[k] for k in ("schema", "latest", "minimum_supported", "upgrade_deadline", "published_at")}


def cache_path(directory=None):
    directory = directory or Path.home() / ".local/share/fpr-nexus-history"
    path = directory / "version-policy.json"
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Version policy paths must not contain symbolic links")
    return path


def evaluate(policy, current=__version__, now=None):
    now = now or datetime.now(timezone.utc)
    policy = validate(policy)
    below = version(current) < version(policy["minimum_supported"])
    due = policy["upgrade_deadline"] is None or now >= instant(policy["upgrade_deadline"])
    status = "required" if below and due else "scheduled" if below else "available" if version(current) < version(policy["latest"]) else "current"
    return {"status": status, "installed_version": current, **policy, "repository": REPOSITORY,
            "next_step": "Refresh the installed plugin in Codex, then run tvlk-ai-router update prepare. Keep the setup window open and quit clients when prompted.",
            "enforcement": "Controls Nexus entry points only. Existing Codex settings and direct client use are not blocked."}


def check(directory=None, current=__version__, refresh=False, now=None):
    now = now or datetime.now(timezone.utc)
    path = cache_path(directory)
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text())
            validate(cached["policy"])
            instant(cached["checked_at"])
        except (ValueError, KeyError, TypeError, AttributeError):
            cached = None
    error = None
    if refresh:
        try:
            request = Request(POLICY_URL, headers={"User-Agent": "FPR-Nexus/" + current})
            with urlopen(request, timeout=3) as response:
                if response.geturl() != POLICY_URL:
                    raise ValueError("Version policy redirects are not accepted")
                raw = response.read(16385)
                if len(raw) > 16384:
                    raise ValueError("Version policy is too large")
                policy = validate(json.loads(raw))
            if cached and instant(policy["published_at"]) < instant(cached["policy"]["published_at"]):
                raise ValueError("An older policy was returned; keeping the last known policy")
            cached = {"checked_at": now.isoformat(), "policy": policy}
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".policy-", dir=path.parent)
            try:
                with os.fdopen(fd, "w") as stream:
                    json.dump(cached, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            error = type(exc).__name__
    if not cached:
        return {"status": "unknown", "installed_version": current, "fetch_error": error,
                "message": "No verified policy is available. Existing routing continues; retry update check.", "repository": REPOSITORY}
    return {**evaluate(cached["policy"], current, now), "checked_at": cached["checked_at"],
            "stale": now - instant(cached["checked_at"]) > timedelta(hours=6), "fetch_error": error}


def require_supported(directory=None, current=__version__):
    result = check(directory, current)
    if result["status"] == "required":
        raise ValueError("FPR Nexus upgrade required. Refresh the plugin and run tvlk-ai-router update prepare. Review, disable and recovery remain available.")
