import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_router as fixtures
from test_shell import installer
from tvlk_ai_router.config import RouterError
from tvlk_ai_router.failed_plugin import recognized_failed_plugin
from tvlk_ai_router.storage import inventory, snapshot


class FailedPluginTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RouterTests()
        self.f.setUp()
        self.home = self.f.root
        self.data = self.home / ".local/share/tvlk-ai-router"
        self.store = self.data / "backups"
        self.root = self.home / ".local/share/tvlk-ai-router-plugin/runtime"
        self.root.mkdir(parents=True)
        (self.root / "shell-installation.json").write_text(json.dumps({"runtime": str(self.root), "distribution": "plugin"}))
        self.config = self.home / ".config/tvlk-ai-router"
        self.shared = self.home / ".agents"
        self.user = patch("pathlib.Path.home", return_value=self.home)
        self.env = patch.dict(os.environ, {"HOME": str(self.home), "CODEX_HOME": str(self.f.home)})
        self.user.start()
        self.env.start()
        with patch("tvlk_ai_router.storage.os.rename", side_effect=PermissionError(13, "denied")):
            with self.assertRaises(RouterError):
                snapshot(self.store, [self.f.home, self.shared, self.config], "baseline", None, self.f.home)
        self.partial = next(self.store.glob("*.partial"))
        self.partial.chmod(0o500)  # The failed 1.4.0 setup sealed this before rename.

    def tearDown(self):
        self.env.stop()
        self.user.stop()
        self.f.tearDown()

    def test_preflight_recognizes_verified_partial_without_mutation(self):
        before = inventory([self.data, self.root, self.f.home])
        self.assertTrue(recognized_failed_plugin(self.root))
        installer.preflight(self.root)
        self.assertEqual(inventory([self.data, self.root, self.f.home]), before)

    def test_final_named_baseline_without_saved_state_is_recognized(self):
        self.partial.chmod(0o700)
        final = self.store / self.partial.name.removesuffix(".partial")
        self.partial.rename(final)
        final.chmod(0o500)
        self.assertTrue(recognized_failed_plugin(self.root))

    def test_damaged_blob_or_missing_completion_is_rejected(self):
        blob = next((self.partial / "files").iterdir())
        blob.chmod(0o600)
        original = blob.read_bytes()
        blob.write_bytes(b"damaged")
        self.assertFalse(recognized_failed_plugin(self.root))
        blob.write_bytes(original)
        self.partial.chmod(0o700)
        (self.partial / "COMPLETE").unlink()
        self.assertFalse(recognized_failed_plugin(self.root))

    def test_saved_runtime_configuration_and_transactions_are_rejected(self):
        for path in [self.root / "src", self.root / "active.json", self.data / "transaction.json", self.data / "state.json", self.data / "unknown"]:
            with self.subTest(path=path):
                path.write_text("{}")
                self.assertFalse(recognized_failed_plugin(self.root))
                path.unlink()
        self.config.mkdir(parents=True)
        (self.config / "router.toml").write_text("user config")
        self.assertFalse(recognized_failed_plugin(self.root))

    def test_native_router_markers_are_rejected(self):
        for name in ("config.toml", "AGENTS.md", "AGENTS.override.md"):
            path = self.f.home / name
            old = path.read_bytes() if path.exists() else None
            path.write_bytes(b"tvlk_ai_route_coding")
            self.assertFalse(recognized_failed_plugin(self.root))
            path.unlink() if old is None else path.write_bytes(old)
        agents = self.f.home / "agents"
        agents.mkdir(exist_ok=True)
        (agents / "tvlk_ai_route_coding.toml").touch()
        self.assertFalse(recognized_failed_plugin(self.root))

    def test_symlink_and_unknown_backup_contents_are_rejected(self):
        self.partial.chmod(0o700)
        link = self.partial / "extra"
        link.symlink_to(self.f.home)
        self.assertFalse(recognized_failed_plugin(self.root))
        link.unlink()
        manifest = self.partial / "manifest.json"
        outside = self.home / "manifest-copy.json"
        outside.write_bytes(manifest.read_bytes())
        manifest.unlink()
        manifest.symlink_to(outside)
        self.assertFalse(recognized_failed_plugin(self.root))

    def test_nonbaseline_manifest_or_wrong_codex_home_is_rejected(self):
        import hashlib
        p = self.partial / "manifest.json"
        complete = self.partial / "COMPLETE"
        original = json.loads(p.read_bytes())
        p.chmod(0o600)
        complete.chmod(0o600)
        for changes in ({"reason": "disable"}, {"router_state": {"status": "enabled"}}, {"codex_home": "/another-user/.codex"}):
            raw = json.dumps({**original, **changes}).encode()
            p.write_bytes(raw)
            complete.write_text(hashlib.sha256(raw).hexdigest())
            self.assertFalse(recognized_failed_plugin(self.root))

    def test_malformed_manifest_and_wrong_runtime_marker_are_rejected(self):
        import hashlib
        p = self.partial / "manifest.json"
        complete = self.partial / "COMPLETE"
        original = p.read_bytes()
        p.chmod(0o600)
        complete.chmod(0o600)
        p.write_bytes(b"[]")
        complete.write_text(hashlib.sha256(b"[]").hexdigest())
        self.assertFalse(recognized_failed_plugin(self.root))
        p.write_bytes(original)
        complete.write_text(hashlib.sha256(original).hexdigest())
        (self.root / "shell-installation.json").write_text('{}')
        self.assertFalse(recognized_failed_plugin(self.root))
