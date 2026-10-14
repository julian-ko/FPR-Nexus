import importlib.util
import io
import contextlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_router as router_fixture
from tvlk_ai_router.config import RouterError
from tvlk_ai_router.desktop import queue_request, perform_request, cancel_request
from tvlk_ai_router.manager import Manager
from tvlk_ai_router.cli import main as cli_main

PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shell_installer", PACKAGE / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.fixture = router_fixture.RouterTests()
        self.fixture.setUp()
        self.runtime = self.fixture.root / "runtime with spaces"
        self.env = patch.dict(os.environ, {"TVLK_ROUTER_SHELL_ROOT": str(self.runtime)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.fixture.tearDown()

    def test_chat_stages_then_executes_and_preserves_ownership_restore(self):
        first = self.fixture.install()["backup_id"]
        m = self.fixture.manager()
        before = (m.home / "config.toml").read_bytes()
        with patch("tvlk_ai_router.desktop.subprocess.run") as launch:
            result = queue_request(m, "disable")
        launch.assert_not_called()
        self.assertIn("'", result["command"])
        self.assertEqual(before, (m.home / "config.toml").read_bytes())
        with patch("tvlk_ai_router.desktop.quiet_check"):
            perform_request(m, result["id"])
        self.assertEqual(self.fixture.manager().state["status"], "disabled")
        self.fixture.manager().restore(first)
        state = self.fixture.manager().state
        self.assertEqual(state["installation_backend"], "shell")
        self.assertEqual(state["shell_runtime"], str(self.runtime))
        self.assertIn(str(self.runtime), (m.skill_dir / "SKILL.md").read_text())

    def test_pending_cancel_stale_and_active_client_checks(self):
        self.fixture.install()
        m = self.fixture.manager()
        req = queue_request(m, "disable")
        with patch("tvlk_ai_router.desktop.quiet_check", side_effect=RouterError("Codex is running")):
            with self.assertRaises(RouterError):
                perform_request(m, req["id"])
        self.assertEqual(self.fixture.manager().state["status"], "enabled")
        m.source.write_bytes(m.source.read_bytes() + b"\n")
        with patch("tvlk_ai_router.desktop.quiet_check"):
            with self.assertRaises(RouterError):
                perform_request(m, req["id"])
        cancel_request(m)
        with patch("tvlk_ai_router.desktop.quiet_check"):
            with self.assertRaises(RouterError):
                perform_request(m, req["id"])

    def test_app_state_guard_has_no_changes(self):
        with patch.dict(os.environ, {"TVLK_ROUTER_SHELL_ROOT": ""}):
            self.fixture.install()
        m = self.fixture
        before = {str(p): p.read_bytes() for p in m.root.rglob("*") if p.is_file()}
        with self.assertRaises(RouterError):
            m.manager()
        self.assertEqual(before, {str(p): p.read_bytes() for p in m.root.rglob("*") if p.is_file()})

    def test_preflight_blocks_app_and_symlink_before_writes(self):
        home = self.fixture.root / "user"
        home.mkdir()
        runtime = home / ".local/share/tvlk-ai-router-plugin/runtime"
        app = home / "Applications/TVLK-OpenAI-Router.app"
        app.mkdir(parents=True)
        with patch("pathlib.Path.home", return_value=home):
            with self.assertRaises(ValueError):
                installer.preflight(runtime)
        self.assertFalse(runtime.exists())
        app.rmdir()
        runtime.mkdir(parents=True)
        (runtime / "shell-installation.json").write_text(json.dumps({"runtime": str(runtime)}))
        (runtime / "runner.py").symlink_to(self.fixture.input)
        with patch("pathlib.Path.home", return_value=home):
            with self.assertRaises(ValueError):
                installer.preflight(runtime)

    def test_installer_rollback_restores_source_and_wrappers(self):
        home = self.fixture.root / "user"
        root = home / ".local/share/tvlk-ai-router-plugin/runtime"
        root.mkdir(parents=True)
        (root / "shell-installation.json").write_text(json.dumps({"runtime": str(root)}))
        (root / ".venv/bin").mkdir(parents=True)
        (root / "src").mkdir()
        (root / "src/old.py").write_text("old source")
        old = {}
        for name in ("runner.py", "tvlk-ai-router", "manage.sh"):
            (root / name).write_bytes(name.encode())
            old[name] = (root / name).read_bytes()
        def run(args, **kwargs):
            if "shell-install" in args:
                raise subprocess.CalledProcessError(4, args)
            return subprocess.CompletedProcess(args, 0)
        with patch("pathlib.Path.home", return_value=home), patch.object(installer.subprocess, "run", side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                installer.install(PACKAGE)
        self.assertEqual((root / "src/old.py").read_text(), "old source")
        for name in old:
            self.assertEqual((root / name).read_bytes(), old[name])

    def test_shell_entry_rejects_missing_and_old_python(self):
        missing = subprocess.run(["bash", str(PACKAGE / "install.sh"), "--python", "/not/a/python"], capture_output=True, text=True)
        self.assertEqual(missing.returncode, 2)
        wrong = self.fixture.root / "old python"
        wrong.write_text("#!/bin/bash\nexit 2\n")
        wrong.chmod(0o700)
        old = subprocess.run(["bash", str(PACKAGE / "install.sh"), "--python", str(wrong)], capture_output=True, text=True)
        self.assertEqual(old.returncode, 2)
        self.assertIn("Python 3.11", old.stderr)

    def test_failed_041_first_bootstrap_reuses_environment_on_retry(self):
        import shutil
        home = self.fixture.root / "retry user"
        home.mkdir()
        shutil.copytree(self.fixture.home, home / ".codex")
        names = {"packages", "tui-thread-reference-capabilities", "future-client-data"}
        for name in names:
            (home / ".codex" / name).mkdir()
            (home / ".codex" / name / "runtime.bin").write_bytes(b"runtime data")
        runtime = home / ".local/share/tvlk-ai-router-plugin/runtime"
        real_run = subprocess.run
        def run(args, **kwargs):
            if "shell-install" in args:
                index = args.index("shell-install")
                with patch.dict(os.environ, {"TVLK_ROUTER_SHELL_ROOT": str(runtime), "TVLK_ROUTER_BACKEND": "plugin"}), patch("tvlk_ai_router.cli.quiet_check"):
                    code = cli_main(args[index:])
                if code:
                    raise subprocess.CalledProcessError(code, args)
                return subprocess.CompletedProcess(args, 0)
            return real_run(args, **kwargs)
        with patch("pathlib.Path.home", return_value=home), patch.dict(os.environ, {"HOME": str(home), "CODEX_HOME": str(home / ".codex")}), patch.object(installer.subprocess, "run", side_effect=run), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            before = (home / ".codex/config.toml").read_bytes()
            # Reproduce the old release's failure after bootstrap, before configuration writes.
            with patch.object(Manager, "report", side_effect=RouterError("Unclassified user files found", 4)):
                with self.assertRaises(subprocess.CalledProcessError):
                    installer.install(PACKAGE, self.fixture.input)
            self.assertTrue((runtime / ".venv/bin/python").exists())
            self.assertTrue((runtime / "shell-installation.json").exists())
            self.assertFalse((runtime / "src").exists())
            self.assertFalse((home / ".local/share/tvlk-ai-router/state.json").exists())
            self.assertTrue((home / ".local/share/tvlk-ai-router/lock").exists())
            self.assertEqual((home / ".codex/config.toml").read_bytes(), before)
            interpreter_inode = (runtime / ".venv/bin/python").stat().st_ino
            installer.install(PACKAGE, self.fixture.input)
            self.assertEqual((runtime / ".venv/bin/python").stat().st_ino, interpreter_inode)
            self.assertTrue((home / ".local/share/tvlk-ai-router/state.json").exists())
            self.assertTrue((runtime / "src").exists())
            for name in names:
                self.assertEqual((home / ".codex" / name / "runtime.bin").read_bytes(), b"runtime data")

    def test_retry_does_not_allow_unowned_backups_or_transactions(self):
        home = self.fixture.root / "retry guard"
        root = home / ".local/share/tvlk-ai-router-plugin/runtime"
        root.mkdir(parents=True)
        (root / "shell-installation.json").write_text(json.dumps({"runtime": str(root), "distribution": "plugin"}))
        data = home / ".local/share/tvlk-ai-router"
        data.mkdir(parents=True)
        (data / "lock").write_bytes(b"")
        with patch("pathlib.Path.home", return_value=home):
            installer.preflight(root)
            (data / "transaction.json").write_bytes(b"{}")
            with self.assertRaises(ValueError):
                installer.preflight(root)
        self.assertEqual((data / "transaction.json").read_bytes(), b"{}")

    def test_clean_offline_environment_install_and_reinstall_preserve_config(self):
        home = self.fixture.root / "clean user"
        home.mkdir()
        import shutil
        shutil.copytree(self.fixture.home, home / ".codex")
        runtime = home / ".local/share/tvlk-ai-router-plugin/runtime"
        real_run = subprocess.run
        def run(args, **kwargs):
            if "shell-install" in args:
                index = args.index("shell-install")
                with patch.dict(os.environ, {"TVLK_ROUTER_SHELL_ROOT": str(runtime), "TVLK_ROUTER_BACKEND": "plugin"}), patch("tvlk_ai_router.cli.quiet_check"):
                    code = cli_main(args[index:])
                if code:
                    raise subprocess.CalledProcessError(code, args)
                return subprocess.CompletedProcess(args, 0)
            return real_run(args, **kwargs)
        with patch("pathlib.Path.home", return_value=home), patch.dict(os.environ, {"HOME": str(home), "CODEX_HOME": str(home / ".codex")}), patch.object(installer.subprocess, "run", side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            installer.install(PACKAGE, self.fixture.input)
            state_path = home / ".local/share/tvlk-ai-router/state.json"
            baseline = json.loads(state_path.read_text())["baseline"]
            config = home / ".config/tvlk-ai-router/router.toml"
            custom = config.read_text().replace('reasoning_effort = "medium"', 'reasoning_effort = "low"', 1)
            config.write_text(custom)
            installer.install(PACKAGE)
            self.assertEqual(config.read_text(), custom)
            self.assertEqual(json.loads(state_path.read_text())["baseline"], baseline)
            result = real_run([str(runtime / ".venv/bin/python"), "-I", str(runtime / "runner.py"), "chat", "help"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Terminal", result.stdout)
            self.assertNotIn("click Run", result.stdout)
            self.assertTrue((runtime / "tvlk-ai-router").stat().st_mode & 0o100)


if __name__ == "__main__":
    unittest.main()
