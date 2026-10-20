import importlib.util
import json
import os
import shutil
import shlex
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_plugin as fixtures

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "scripts"))
import runtime as versions


class LiveUpdateTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PluginTests()
        self.f.setUp()
        self.f.install()
        self.root = self.f.runtime
        self.root.mkdir(parents=True)
        (self.root / "shell-installation.json").write_text(json.dumps({"runtime": str(self.root), "distribution": "plugin"}))
        (self.root / ".venv/bin").mkdir(parents=True)
        python = self.root / ".venv/bin/python"
        python.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
        python.chmod(0o700)
        self.env = patch.dict(os.environ, {"HOME": str(self.f.fixture.root), "CODEX_HOME": str(self.f.fixture.home)})
        self.env.start()
        versions.initialize(PACKAGE, self.root)
        self.initial = versions.active(self.root)["current"]["version"]
        self.package = self.f.fixture.root / "candidate"
        shutil.copytree(PACKAGE, self.package, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))
        number = ".".join(map(str, (*versions.version(self.initial)[:2], versions.version(self.initial)[2] + 1)))
        self.next_version = number
        manifest = json.loads((self.package / "plugin.json").read_text())
        manifest["version"] = number
        (self.package / "plugin.json").write_text(json.dumps(manifest))
        (self.package / "src/tvlk_ai_router/__init__.py").write_text('__version__ = "' + number + '"\n')

    def tearDown(self):
        self.env.stop()
        self.f.tearDown()

    def preserved(self):
        m = self.f.fixture.manager()
        paths = [m.state_file, m.source, m.home / "config.toml"]
        paths += list((m.home / "agents").glob("*.toml"))
        paths += [p for p in m.store().rglob("*") if p.is_file()]
        return {str(p): p.read_bytes() for p in paths if p.exists()}

    def test_update_and_retry_leave_settings_state_backups_and_usage_untouched(self):
        history = self.f.fixture.root / ".local/share/fpr-nexus-history"
        history.mkdir()
        (history / "retained.json").write_text('{"keep":true}')
        before = self.preserved()
        self.assertEqual(versions.sync(self.package, self.root)["status"], "updated")
        self.assertEqual(versions.sync(self.package, self.root)["status"], "current")
        self.assertEqual(self.preserved(), before)
        self.assertEqual((history / "retained.json").read_text(), '{"keep":true}')
        self.assertTrue((self.root / "releases" / self.initial).exists())

    def test_disabled_state_survives_live_upgrade(self):
        self.f.fixture.manager().change("disable")
        before = self.preserved()
        self.assertEqual(versions.sync(self.package, self.root)["status"], "updated")
        self.assertEqual(self.preserved(), before)
        self.assertEqual(self.f.fixture.manager().state["status"], "disabled")

    def test_cold_upgrade_preserves_disabled_and_restored_state(self):
        from tvlk_ai_router.cli import main
        import contextlib
        import io
        m = self.f.fixture.manager()
        baseline = m.state["baseline"]
        for status in ("disabled", "restored"):
            m = self.f.fixture.manager()
            m.change("disable") if status == "disabled" else m.restore(baseline)
            before = self.preserved()
            with patch("tvlk_ai_router.cli.quiet_check"), patch("tvlk_ai_router.migration.quiet_check"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--config-dir", str(self.f.fixture.cfg), "--agents-home", str(self.f.fixture.shared), "shell-install"]), 0)
            self.assertEqual(self.preserved(), before)
            self.assertEqual(self.f.fixture.manager().state["status"], status)

    def test_old_plugin_runtime_requires_one_time_setup_without_mutation(self):
        (self.root / "active.json").unlink()
        before = self.preserved()
        self.assertEqual(versions.sync(self.package, self.root)["status"], "maintenance_required")
        self.assertFalse((self.root / "active.json").exists())
        self.assertEqual(self.preserved(), before)

    def test_restored_state_survives_live_upgrade(self):
        m = self.f.fixture.manager()
        m.restore(m.state["baseline"])
        before = self.preserved()
        self.assertEqual(versions.sync(self.package, self.root)["status"], "updated")
        self.assertEqual(self.preserved(), before)
        self.assertEqual(self.f.fixture.manager().state["status"], "restored")

    def test_native_agent_change_requires_maintenance_without_switch(self):
        p = self.package / "src/tvlk_ai_router/config.py"
        with p.open("a") as stream:
            stream.write('\n_original_agents = native_agents\ndef native_agents(d):\n    return {k: v+b"\\n" for k,v in _original_agents(d).items()}\n')
        before = self.preserved()
        self.assertEqual(versions.sync(self.package, self.root)["status"], "maintenance_required")
        self.assertEqual(versions.active(self.root)["current"]["version"], self.initial)
        self.assertEqual(self.preserved(), before)

    def test_data_contract_change_requires_maintenance(self):
        p = self.package / "runtime.json"
        value = json.loads(p.read_text())
        value["history"] += 1
        p.write_text(json.dumps(value))
        self.assertEqual(versions.sync(self.package, self.root)["status"], "maintenance_required")

    def test_validation_failure_and_pointer_failure_preserve_working_version(self):
        before = (self.root / "active.json").read_bytes()
        with patch.object(versions, "probe", side_effect=ValueError("broken candidate")), self.assertRaises(ValueError):
            versions.sync(self.package, self.root)
        self.assertEqual((self.root / "active.json").read_bytes(), before)
        with patch.object(versions, "atomic", side_effect=OSError("disk full")), self.assertRaises(OSError):
            versions.sync(self.package, self.root)
        self.assertEqual((self.root / "active.json").read_bytes(), before)
        self.assertEqual(versions.sync(self.package, self.root)["status"], "updated")

    def test_rollback_persists_until_explicit_retry_or_newer_package(self):
        versions.sync(self.package, self.root)
        self.assertEqual(versions.sync(self.package, self.root, rollback=True)["status"], "rolled_back")
        self.assertEqual(versions.sync(self.package, self.root)["status"], "held")
        self.assertEqual(versions.active(self.root)["current"]["version"], self.initial)
        self.assertEqual(versions.sync(self.package, self.root, automatic=False)["status"], "updated")

    def test_older_plugin_does_not_downgrade_runtime(self):
        versions.sync(self.package, self.root)
        self.assertEqual(versions.sync(PACKAGE, self.root)["version"], self.next_version)

    def test_chat_entry_activates_update_and_setup_needs_no_window(self):
        for name in ("runner.py", "runtime.py", "tvlk-ai-router"):
            shutil.copy2(PACKAGE / "scripts" / name, self.root / name)
        (self.root / "tvlk-ai-router").chmod(0o700)
        env = {**os.environ, "HOME": str(self.f.fixture.root)}
        result = subprocess.run(["bash", str(self.package / "scripts/chat.sh"), "help"],
                                capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("update rollback", result.stdout)
        self.assertEqual(versions.active(self.root)["current"]["version"], self.next_version)
        result = subprocess.run([sys.executable, "-I", str(self.package / "scripts/setup.py"), "--open"],
                                capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "current")
        self.assertFalse((self.root.parent / "setup").exists())

    def test_concurrent_install_and_modified_release_are_rejected(self):
        with versions.locked(self.root):
            self.assertEqual(versions.sync(self.package, self.root)["status"], "busy")
        payload = versions.selected_source(self.root)
        (payload / "unexpected.py").write_text("# manual edit")
        with self.assertRaisesRegex(ValueError, "changed"):
            versions.sync(self.package, self.root)

    def test_configuration_changes_and_pending_recovery_block_activation(self):
        from tvlk_ai_router.storage import lock
        before = (self.root / "active.json").read_bytes()
        with lock(self.f.fixture.data):
            self.assertEqual(versions.sync(self.package, self.root)["status"], "busy")
        pending = self.f.fixture.data / "transaction.json"
        pending.write_text('{}')
        with self.assertRaisesRegex(ValueError, "pending"):
            versions.sync(self.package, self.root)
        self.assertEqual((self.root / "active.json").read_bytes(), before)

    def test_unknown_roots_and_symlinks_are_not_overwritten(self):
        pointer = self.root / "active.json"
        saved = pointer.read_bytes()
        pointer.unlink()
        self.assertEqual(versions.sync(self.package, self.root)["status"], "maintenance_required")
        outside = self.f.fixture.root / "outside.json"
        outside.write_bytes(saved)
        pointer.symlink_to(outside)
        with self.assertRaises(ValueError):
            versions.sync(self.package, self.root)
        self.assertEqual(outside.read_bytes(), saved)

    def test_running_process_keeps_pinned_source_after_activation(self):
        code = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runtime import selected_source
sys.path.insert(0, str(selected_source(Path(sys.argv[2]))))
from tvlk_ai_router import __version__
print(__version__, flush=True)
sys.stdin.readline()
from tvlk_ai_router.cli import __version__ as later
print(later, flush=True)
'''
        command = [sys.executable, "-I", "-c", code, str(PACKAGE / "scripts"), str(self.root)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), self.initial)
            versions.sync(self.package, self.root)
            output, error = process.communicate("\n", timeout=15)
            self.assertEqual(process.returncode, 0, error)
            self.assertEqual(output.strip(), self.initial)
            new = subprocess.run(command, input="\n", capture_output=True, text=True, check=True, timeout=15)
            self.assertEqual(new.stdout.splitlines(), [self.next_version, self.next_version])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
