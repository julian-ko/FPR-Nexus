import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_router as fixtures
from tvlk_ai_router.config import RouterError, strip_block
from tvlk_ai_router.migration import migrate, locations
from tvlk_ai_router.desktop import dispatch
from tvlk_ai_router.cli import parser
from tvlk_ai_router.storage import inventory, lock, quiet_check

PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_helper", PACKAGE / "scripts/setup.py")
setup_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_helper)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RouterTests()
        self.f.setUp()
        for name in ("packages", "tui-thread-reference-capabilities", "future-client-data"):
            directory = self.f.home / name
            directory.mkdir()
            (directory / "data").write_bytes(b"preserve across legacy migration")
        old_backups = str(self.f.backups)
        self.f.cfg = self.f.root / ".config/tvlk-ai-router"
        self.f.shared = self.f.root / ".agents"
        self.f.data = self.f.root / ".local/share/tvlk-ai-router"
        self.f.backups = self.f.data / "backups"
        self.f.input.write_text(self.f.input.read_text().replace(old_backups, str(self.f.backups)))
        self.runtime = self.f.root / ".local/share/tvlk-ai-router-plugin/runtime"
        self.user = patch("pathlib.Path.home", return_value=self.f.root)
        self.user.start()
        self.env = patch.dict(os.environ, {"CODEX_HOME": str(self.f.home), "TVLK_ROUTER_SHELL_ROOT": "", "TVLK_ROUTER_BACKEND": "shell"})
        self.env.start()
        self.quiet = patch("tvlk_ai_router.migration.quiet_check")
        self.quiet.start()

    def tearDown(self):
        self.quiet.stop()
        self.env.stop()
        self.user.stop()
        self.f.tearDown()

    def old(self, backend="app", disabled=False):
        if backend == "shell":
            shell = locations()["shell-runtime"]
            shell.mkdir(parents=True)
            (shell / "shell-installation.json").write_text(json.dumps({"runtime": str(shell), "distribution": "shell"}))
            (shell / "old-program").write_text("old shell")
            os.environ["TVLK_ROUTER_SHELL_ROOT"] = str(shell)
        else:
            app = locations()["application"]
            app.mkdir(parents=True)
            (app / "old-program").write_text("old app")
        with lock(self.f.data):
            baseline = self.f.install()["backup_id"]
        if disabled:
            self.f.manager().change("disable")
        original = self.f.manager().state
        os.environ["TVLK_ROUTER_SHELL_ROOT"] = str(self.runtime)
        os.environ["TVLK_ROUTER_BACKEND"] = "plugin"
        return baseline, original

    def migrate(self):
        with patch("tvlk_ai_router.migration.verify_app"):
            migrate(self.runtime)
        for name in ("packages", "tui-thread-reference-capabilities", "future-client-data"):
            self.assertEqual((self.f.home / name / "data").read_bytes(), b"preserve across legacy migration")

    def test_app_migration_preserves_config_backups_and_restore(self):
        baseline, old = self.old()
        source = self.f.cfg / "router.toml"
        source.write_bytes(source.read_bytes() + b"\n# team custom setting\n")
        custom = source.read_bytes()
        snapshots = inventory([self.f.backups])
        self.migrate()
        m = self.f.manager()
        self.assertEqual(m.state["status"], "disabled")
        self.assertEqual(m.state["baseline"], baseline)
        self.assertEqual(m.state["installed_at"], old["installed_at"])
        self.assertEqual(m.source.read_bytes(), custom)
        after = inventory([self.f.backups])
        for path, info in snapshots.items():
            if info["type"] == "file":
                self.assertEqual(after[path], info)
        self.assertTrue(all(not p.exists() for p in locations().values()))
        self.assertTrue((self.runtime.parent / "legacy/application/old-program").exists())
        m.change("enable")
        self.assertFalse(m.skill_dir.exists())
        self.assertIsNone(strip_block((m.home / "AGENTS.md").read_text())[1])
        active_old = next(b["id"] for b in m.backups() if b["reason"] == "disable")
        m.restore(active_old)
        self.assertEqual(m.state["installation_backend"], "plugin")
        self.assertEqual(m.drift(), [])
        self.assertFalse(m.skill_dir.exists())
        self.assertIsNone(strip_block((m.home / "AGENTS.md").read_text())[1])
        m.change("disable")
        self.assertEqual((m.home / "config.toml").read_bytes(), self.f.original)
        m.restore(baseline)
        self.assertEqual(m.state["installation_backend"], "plugin")

    def test_shell_disabled_and_repeat_migration(self):
        self.old("shell", disabled=True)
        self.migrate()
        self.assertTrue((self.runtime.parent / "legacy/shell-runtime/old-program").exists())
        before = inventory([self.f.data, self.f.cfg, self.f.home])
        self.migrate()
        self.assertEqual(inventory([self.f.data, self.f.cfg, self.f.home]), before)

    def cli_migration(self, status):
        from tvlk_ai_router.cli import main
        baseline, original = self.old("shell", disabled=status == "disabled")
        if status == "restored":
            with patch.dict(os.environ, {"TVLK_ROUTER_BACKEND": "shell", "TVLK_ROUTER_SHELL_ROOT": str(locations()["shell-runtime"])}):
                self.f.manager().restore(baseline)
        arguments = ["--codex-home", str(self.f.home), "--config-dir", str(self.f.cfg),
                     "--data-dir", str(self.f.data), "--agents-home", str(self.f.shared), "shell-install"]
        with patch("tvlk_ai_router.cli.quiet_check"):
            self.assertEqual(main(arguments), 0)
            self.assertEqual(main(arguments), 0)
        m = self.f.manager()
        self.assertEqual(m.state["status"], status)
        self.assertEqual(m.state["baseline"], baseline)
        self.assertEqual(m.state["installed_at"], original["installed_at"])
        self.assertNotIn("migration_resume_enabled", m.state)
        self.assertEqual(m.drift(), [])

    def test_cli_migration_resumes_enabled_router(self):
        self.cli_migration("enabled")

    def test_cli_migration_keeps_disabled_router(self):
        self.cli_migration("disabled")

    def test_cli_migration_keeps_restored_router(self):
        self.cli_migration("restored")
        self.f.manager().change("enable")

    def test_edited_skill_stops_before_disabling(self):
        self.old()
        skill = locations()["management-skill"] / "SKILL.md"
        skill.write_bytes(skill.read_bytes() + b"\nuser edit\n")
        before = inventory([self.f.data, self.f.cfg, self.f.home, self.f.shared])
        with self.assertRaisesRegex(RouterError, "Skill was edited"):
            self.migrate()
        self.assertEqual(inventory([self.f.data, self.f.cfg, self.f.home, self.f.shared]), before)
        self.assertTrue(locations()["application"].exists())

    def test_interrupted_moves_resume(self):
        self.old()
        original = Path.rename
        def fail_skill(path, target):
            if path == locations()["management-skill"]:
                raise OSError("simulated interruption")
            return original(path, target)
        with patch.object(Path, "rename", fail_skill):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.migrate()
        self.assertTrue((self.runtime.parent / "legacy/application").exists())
        self.migrate()
        self.assertEqual(self.f.manager().state["installation_backend"], "plugin")
        self.f.manager().change("enable")

    def test_active_client_or_broken_backup_leaves_old_install_untouched(self):
        self.old()
        before = inventory([self.f.data, self.f.cfg, self.f.home])
        with patch("tvlk_ai_router.migration.quiet_check", side_effect=RouterError("active client")):
            with self.assertRaisesRegex(RouterError, "active client"):
                self.migrate()
        self.assertEqual(inventory([self.f.data, self.f.cfg, self.f.home]), before)
        with patch("tvlk_ai_router.manager.Manager.backups", return_value=[{"verified": False}]):
            with self.assertRaisesRegex(RouterError, "backups"):
                self.migrate()
        self.assertEqual(inventory([self.f.data, self.f.cfg, self.f.home]), before)

    def test_setup_handoff_preserves_state_and_handles_spaces(self):
        self.old("shell")
        before = inventory([self.f.data, self.f.cfg, self.f.home])
        command = setup_helper.prepare(PACKAGE, sys.executable)
        self.assertEqual(inventory([self.f.data, self.f.cfg, self.f.home]), before)
        self.assertEqual(subprocess.run(["bash", "-n", str(command)]).returncode, 0)
        self.assertTrue((command.parent / "package/install.sh").exists())
        self.assertIn(str(self.f.home), command.read_text())

    def test_status_reports_enabled_state_and_pending_request(self):
        self.old()
        self.migrate()
        self.f.manager().change("enable")
        result = dispatch(parser().parse_args(["chat", "status"]))
        self.assertEqual(result["status"], "enabled")
        self.assertEqual(result["pending_request"]["status"], "none")

    def test_restored_old_install_can_migrate_with_missing_source(self):
        baseline, _ = self.old()
        from tvlk_ai_router.migration import legacy_environment
        with legacy_environment():
            self.f.manager().restore(baseline)
        self.assertFalse((self.f.cfg / "router.toml").exists())
        self.migrate()
        m = self.f.manager()
        m.change("enable")
        self.assertEqual(m.state["baseline"], baseline)
        self.assertFalse(m.skill_dir.exists())

    def test_retry_rejects_changed_archived_program(self):
        self.old()
        original = Path.rename
        def fail_skill(path, target):
            if path == locations()["management-skill"]:
                raise OSError("interrupted")
            return original(path, target)
        with patch.object(Path, "rename", fail_skill):
            with self.assertRaises(OSError):
                self.migrate()
        (self.runtime.parent / "legacy/application/old-program").write_text("changed")
        with self.assertRaisesRegex(RouterError, "changed during migration"):
            self.migrate()
        self.assertTrue(locations()["management-skill"].exists())

    def test_old_app_window_blocks_migration(self):
        process = subprocess.CompletedProcess([], 0, stdout="99999 /test/TVLK-OpenAI-Router.app/Contents/MacOS/RouterInstaller\n")
        with patch("tvlk_ai_router.storage.subprocess.run", return_value=process):
            with self.assertRaisesRegex(RouterError, "old Router app"):
                quiet_check(include_router=True)


if __name__ == "__main__":
    unittest.main()
