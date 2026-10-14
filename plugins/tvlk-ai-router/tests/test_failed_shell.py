import fcntl
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_migration as migration_fixture
from test_migration import PACKAGE, setup_helper
from test_shell import installer
from tvlk_ai_router.cli import main as cli_main
from tvlk_ai_router.failed_shell import recognized_failed_shell
from tvlk_ai_router.migration import locations, migrate
from tvlk_ai_router.config import RouterError
from tvlk_ai_router.storage import inventory


class FailedShellTests(unittest.TestCase):
    def setUp(self):
        self.fixture = migration_fixture.MigrationTests()
        self.fixture.setUp()
        self.f = self.fixture.f
        self.runtime = self.fixture.runtime
        self.runtime.parent.mkdir(parents=True)
        self.shell = locations()["shell-runtime"]
        self.shell.mkdir(parents=True)
        (self.shell / "shell-installation.json").write_text(json.dumps({"runtime": str(self.shell), "distribution": "shell"}))
        for name in ("runner.py", "manage.sh", "tvlk-ai-router"):
            source = (PACKAGE / "scripts" / name).read_text()
            source = source.replace('os.environ["TVLK_ROUTER_BACKEND"] = "plugin"\n', '')
            (self.shell / name).write_text(source)
        (self.shell / ".venv/bin").mkdir(parents=True)
        (self.shell / ".venv/bin/python").symlink_to(sys.executable)
        self.f.data.mkdir(parents=True)
        (self.f.data / "lock").write_bytes(b"")
        os.environ["TVLK_ROUTER_BACKEND"] = "plugin"
        os.environ["TVLK_ROUTER_SHELL_ROOT"] = str(self.runtime)

    def tearDown(self):
        self.fixture.tearDown()

    def test_prepare_and_preflight_are_read_only_for_failed_shell(self):
        roots = [self.shell, self.f.data, self.f.home, self.f.cfg]
        before = inventory(roots)
        self.assertTrue(recognized_failed_shell())
        command = setup_helper.prepare(PACKAGE, sys.executable)
        installer.preflight(self.runtime)
        self.assertTrue(command.exists())
        self.assertEqual(inventory(roots), before)

    def test_archive_preserves_files_then_fresh_install_can_complete(self):
        before = {str(Path(p).relative_to(self.shell)): value for p, value in inventory([self.shell]).items()}
        migrate(self.runtime)
        destination = self.runtime.parent / "failed-shell-runtime"
        after = {str(Path(p).relative_to(destination)): value for p, value in inventory([destination]).items()}
        self.assertEqual(before, after)
        self.assertFalse(self.shell.exists())
        self.f.manager().change("install", str(self.f.input))
        self.assertEqual(self.f.manager().state["installation_backend"], "plugin")
        self.assertEqual(self.f.manager().drift(), [])

    def test_real_plugin_bootstrap_after_failed_shell(self):
        for name in ("app-server-control", "app-server-daemon", "archived_sessions", "macos",
                     "tui-thread-preference-capabilities"):
            directory = self.f.home / name
            directory.mkdir()
            (directory / "fixture").write_text("preserve me")
        (self.f.home / "config.toml.before-tvlk-1.0.4-20261014-102443").write_bytes(self.f.original)
        real_run = subprocess.run
        def run(args, **kwargs):
            if "shell-install" in args:
                with patch("tvlk_ai_router.cli.quiet_check"):
                    code = cli_main(args[args.index("shell-install"):])
                if code:
                    raise subprocess.CalledProcessError(code, args)
                return subprocess.CompletedProcess(args, 0)
            return real_run(args, **kwargs)
        with patch.dict(os.environ, {"HOME": str(self.f.root)}), patch.object(installer.subprocess, "run", side_effect=run):
            installer.install(PACKAGE, self.f.input)
        self.assertTrue((self.runtime / ".venv/bin/python").exists())
        self.assertTrue((self.runtime.parent / "failed-shell-runtime/runner.py").exists())
        self.assertEqual(self.f.manager().state["installation_backend"], "plugin")
        self.assertEqual(self.f.manager().drift(), [])

    def test_uncertain_history_is_not_treated_as_failed_bootstrap(self):
        for path, data in ((self.f.data / "transaction.json", b"{}"),
                           (self.f.data / "backup.json", b"backup"),
                           (self.f.cfg / "router.toml", b"settings"),
                           (self.shell / "src/old.py", b"program"),
                           (self.shell / "notes.txt", b"user file")):
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                self.assertFalse(recognized_failed_shell())
                with self.assertRaises(RouterError):
                    migrate(self.runtime)
                self.assertEqual(path.read_bytes(), data)
                path.unlink()
                if path.parent == self.shell / "src":
                    path.parent.rmdir()
        self.assertTrue(recognized_failed_shell())

    def test_edited_wrapper_and_native_router_settings_are_rejected(self):
        runner = self.shell / "runner.py"
        original = runner.read_bytes()
        runner.write_bytes(original + b"# modified\n")
        self.assertFalse(recognized_failed_shell())
        runner.write_bytes(original)
        config = self.f.home / "config.toml"
        config.write_bytes(config.read_bytes() + b'\n[agents.tvlk_ai_route_coding]\n')
        self.assertFalse(recognized_failed_shell())

    def test_active_client_and_concurrent_shell_installer_block_move(self):
        with patch("tvlk_ai_router.migration.quiet_check", side_effect=RouterError("active client", 4)):
            with self.assertRaisesRegex(RouterError, "active client"):
                migrate(self.runtime)
        self.assertTrue(self.shell.exists())
        with (self.shell.parent / ".installation.lock").open("w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RouterError, "Shell installer"):
                migrate(self.runtime)
        self.assertTrue(self.shell.exists())

    def test_interrupted_move_can_retry_and_archive_collision_cannot_overwrite(self):
        with patch.object(Path, "rename", side_effect=OSError("interrupted")):
            with self.assertRaisesRegex(OSError, "interrupted"):
                migrate(self.runtime)
        self.assertTrue(self.shell.exists())
        destination = self.runtime.parent / "failed-shell-runtime"
        destination.mkdir()
        with self.assertRaisesRegex(RouterError, "archive already exists"):
            migrate(self.runtime)
        destination.rmdir()
        migrate(self.runtime)
        migrate(self.runtime)
        self.assertTrue(destination.is_dir())

    def test_missing_marker_or_symlink_is_not_accepted(self):
        marker = self.shell / "shell-installation.json"
        marker.unlink()
        self.assertFalse(recognized_failed_shell())
        target = self.f.root / "marker.json"
        target.write_text(json.dumps({"runtime": str(self.shell), "distribution": "shell"}))
        marker.symlink_to(target)
        self.assertFalse(recognized_failed_shell())
