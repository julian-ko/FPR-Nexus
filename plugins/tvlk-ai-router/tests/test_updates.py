import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from tvlk_ai_router.updates import check, evaluate, validate, require_supported, POLICY_URL


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name).resolve()
        self.now = datetime(2026, 10, 15, tzinfo=timezone.utc)
        self.policy = {"schema": 1, "latest": "1.2.0", "minimum_supported": "1.1.0",
                       "upgrade_deadline": "2026-10-16T00:00:00Z", "published_at": "2026-10-15T00:00:00Z"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_deadline_semver_and_available(self):
        self.assertEqual(evaluate(self.policy, "1.0.8", self.now)["status"], "scheduled")
        self.assertEqual(evaluate(self.policy, "1.1.0", self.now)["status"], "available")
        self.assertEqual(evaluate(self.policy, "1.10.0", self.now)["status"], "current")
        self.assertEqual(evaluate(self.policy, "1.0.8", datetime(2026, 10, 16, tzinfo=timezone.utc))["status"], "required")
        with self.assertRaises(ValueError):
            validate({**self.policy, "minimum_supported": "2.0.0"})
        with self.assertRaises(ValueError):
            validate({**self.policy, "upgrade_deadline": "2026-10-16"})

    def test_network_failure_retains_required_policy(self):
        self.policy["upgrade_deadline"] = None
        (self.directory / "version-policy.json").write_text(json.dumps({"policy": self.policy, "checked_at": self.now.isoformat()}))
        with patch("tvlk_ai_router.updates.urlopen", side_effect=URLError("offline")):
            result = check(self.directory, "1.0.8", refresh=True, now=self.now)
        self.assertEqual(result["status"], "required")
        self.assertIsNotNone(result["fetch_error"])
        with self.assertRaisesRegex(ValueError, "upgrade required"):
            require_supported(self.directory, "1.0.8")
        (self.directory / "version-policy.json").unlink()
        with patch("tvlk_ai_router.updates.urlopen", side_effect=URLError("offline")):
            self.assertEqual(check(self.directory, refresh=True)["status"], "unknown")

    def test_refresh_cache_and_no_remote_command_fields(self):
        with patch("tvlk_ai_router.updates.urlopen") as fetch:
            response = fetch.return_value.__enter__.return_value
            response.geturl.return_value = POLICY_URL
            response.read.return_value = json.dumps({**self.policy, "command": "do not execute"}).encode()
            result = check(self.directory, refresh=True, now=self.now)
            self.assertEqual(result["latest"], "1.2.0")
            self.assertNotIn("command", (self.directory / "version-policy.json").read_text())
            response.read.return_value = b"x" * 16385
            self.assertIsNotNone(check(self.directory, refresh=True)["fetch_error"])
        with patch("tvlk_ai_router.updates.urlopen", side_effect=AssertionError("cached check must not use network")):
            self.assertEqual(check(self.directory)["latest"], "1.2.0")

    def test_symlink_and_rollback_policy_rejected(self):
        target = self.directory / "outside"
        (self.directory / "version-policy.json").symlink_to(target)
        with self.assertRaises(ValueError):
            check(self.directory)
        self.assertFalse(target.exists())

    def test_prepare_old_package_stops_and_current_package_opens_existing_setup(self):
        import importlib.util
        import subprocess
        package = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("update_script", package / "scripts/update.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, "check", return_value={"status": "available", "latest": "9.0.0"}), \
                patch("sys.argv", ["update.py", "prepare"]), patch("pathlib.Path.home", return_value=self.directory), \
                patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.main(), 4)
            run.assert_not_called()
        with patch.object(module, "check", return_value={"status": "current", "latest": module.__version__}), \
                patch("sys.argv", ["update.py", "prepare"]), patch("pathlib.Path.home", return_value=self.directory), \
                patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 4)) as run:
            self.assertEqual(module.main(), 4)
            self.assertEqual(run.call_args.args[0][-1], "--open")
