import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_router as fixture_module
from tvlk_ai_router.config import RouterError
from tvlk_ai_router.desktop import queue_request, perform_request

PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("router_hook", PACKAGE / "hooks/router.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.RouterTests()
        self.fixture.setUp()
        old_backups = str(self.fixture.backups)
        self.fixture.data = self.fixture.root / ".local/share/tvlk-ai-router"
        self.fixture.backups = self.fixture.data / "backups"
        self.fixture.input.write_text(self.fixture.input.read_text().replace(old_backups, str(self.fixture.backups)))
        self.runtime = self.fixture.root / ".local/share/tvlk-ai-router-plugin/runtime"
        self.env = patch.dict(os.environ, {"TVLK_ROUTER_SHELL_ROOT": str(self.runtime), "TVLK_ROUTER_BACKEND": "plugin"})
        self.env.start()
        self.user = patch("pathlib.Path.home", return_value=self.fixture.root)
        self.user.start()

    def tearDown(self):
        self.user.stop()
        self.env.stop()
        self.fixture.tearDown()

    def install(self):
        return self.fixture.install()

    def payload(self, event="SessionStart", source="vscode", role=None):
        transcript = self.fixture.home / "sessions/session.jsonl"
        transcript.parent.mkdir(exist_ok=True)
        transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": "session", "source": source, "agent_role": role}}) + "\n")
        return {"hook_event_name": event, "session_id": "session", "transcript_path": str(transcript)}

    def test_setup_reinstall_leaves_global_instructions_and_no_standalone_skill(self):
        instruction = self.fixture.home / "AGENTS.md"
        original = instruction.read_bytes()
        first = self.install()["backup_id"]
        self.assertEqual(instruction.read_bytes(), original)
        self.assertFalse(self.fixture.manager().skill_dir.exists())
        m = self.fixture.manager()
        installed = m.state["installed_at"]
        m.source.write_text(m.source.read_text().replace('reasoning_effort = "medium"', 'reasoning_effort = "low"', 1))
        custom = m.source.read_bytes()
        m.change("apply")
        self.assertEqual(m.source.read_bytes(), custom)
        self.assertEqual(m.state["baseline"], first)
        self.assertEqual(m.state["installed_at"], installed)
        self.assertEqual(instruction.read_bytes(), original)
        self.assertEqual(m.state["installation_backend"], "plugin")

    def test_hooks_only_root_enabled_matched_native_configuration(self):
        self.install()
        for event in ("SessionStart", "UserPromptSubmit"):
            payload = self.payload(event)
            before = self.fixture.manager().state_file.read_bytes()
            result = hook.context(payload, self.runtime)
            self.assertEqual(result["hookSpecificOutput"]["hookEventName"], event)
            self.assertIn("tvlk_ai_route_coding", result["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(before, self.fixture.manager().state_file.read_bytes())
        self.assertIsNone(hook.context(self.payload(source={"subagent": {"thread_spawn": {"parent_thread_id": "root"}}}, role="tvlk_ai_route_coding"), self.runtime))
        missing = self.payload()
        missing.pop("transcript_path")
        self.assertIsNone(hook.context(missing, self.runtime))
        self.assertIsNone(hook.context(self.payload(), self.runtime, "future-version"))
        m = self.fixture.manager()
        agent = Path(next(iter(m.state["agent_hashes"])))
        original = agent.read_bytes()
        agent.write_bytes(original + b"\n")
        self.assertIsNone(hook.context(self.payload(), self.runtime))
        agent.write_bytes(original)
        m.change("disable")
        self.assertIsNone(hook.context(self.payload(), self.runtime))

    def test_required_upgrade_keeps_disable_restore_and_history_available(self):
        from tvlk_ai_router.history import report
        baseline = self.install()["backup_id"]
        m = self.fixture.manager()
        result = report(m)
        history = Path(result["history_file"])
        policy = {"schema": 1, "latest": "99.0.0", "minimum_supported": "99.0.0", "upgrade_deadline": None,
                  "published_at": "2026-10-15T00:00:00Z"}
        (history.parent / "version-policy.json").write_text(json.dumps({"checked_at": "2026-10-15T00:00:00Z", "policy": policy}))
        text = hook.context(self.payload(), self.runtime)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("requires an upgrade", text)
        self.assertNotIn("tvlk_ai_route_coding", text)
        with self.assertRaisesRegex(RouterError, "upgrade required"):
            m.change("apply")
        with self.assertRaisesRegex(RouterError, "upgrade required"):
            queue_request(m, "apply")
        m.change("disable")
        m.restore(baseline)
        self.assertTrue(history.is_file())
        self.assertIn("groups", report(self.fixture.manager()))

    def test_absent_global_instructions_remain_absent_through_lifecycle(self):
        instruction = self.fixture.home / "AGENTS.md"
        instruction.unlink()
        first = self.install()["backup_id"]
        self.assertFalse(instruction.exists())
        m = self.fixture.manager()
        m.change("apply")
        self.assertFalse(instruction.exists())
        m.change("disable")
        self.assertFalse(instruction.exists())
        m.change("enable")
        self.assertFalse(instruction.exists())
        m.restore(first)
        self.assertFalse(instruction.exists())

    def test_recovery_is_independent_of_cache_and_preserves_backend(self):
        first = self.install()["backup_id"]
        m = self.fixture.manager()
        request = queue_request(m, "restore", first)
        self.assertIn("tvlk-ai-router-plugin/runtime/manage.sh", request["command"])
        with patch("tvlk_ai_router.desktop.quiet_check"):
            perform_request(m, request["id"])
        m = self.fixture.manager()
        self.assertEqual(m.state["installation_backend"], "plugin")
        self.assertEqual(m.state["status"], "restored")
        self.assertFalse(m.skill_dir.exists())
        self.assertIsNone(hook.context(self.payload(), self.runtime))
        m.change("enable", str(self.fixture.input))
        self.assertEqual(m.state["installation_backend"], "plugin")

    def test_shell_backend_refused_before_changes(self):
        with patch.dict(os.environ, {"TVLK_ROUTER_BACKEND": "shell"}):
            self.install()
        before = self.fixture.data.joinpath("state.json").read_bytes()
        with self.assertRaises(RouterError):
            self.fixture.manager()
        self.assertEqual(self.fixture.data.joinpath("state.json").read_bytes(), before)

    def test_chat_launcher_setup_and_version_guard(self):
        launcher = PACKAGE / "scripts/chat.sh"
        env = {**os.environ, "HOME": str(self.fixture.root), "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")}
        setup = subprocess.run(["bash", str(launcher), "setup"], capture_output=True, text=True, env=env)
        self.assertEqual(setup.returncode, 0)
        self.assertIn("Setup-Router.command", setup.stdout)
        prepared = Path(setup.stdout.split("Setup file: ", 1)[1].strip())
        self.assertTrue(prepared.exists())
        self.assertIn("--install", prepared.read_text())
        self.runtime.mkdir(parents=True)
        engine = self.runtime / "tvlk-ai-router"
        engine.write_text("#!/bin/bash\necho 'TVLK-OpenAI-Router 0.4.2'\n")
        engine.chmod(0o700)
        result = subprocess.run(["bash", str(launcher), "help"], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 4)
        self.assertIn("versions differ", result.stderr)

    def test_actual_isolated_hook_script_and_missing_identity_fail_quiet(self):
        self.install()
        payload = self.payload("UserPromptSubmit")
        import shutil
        shutil.copytree(PACKAGE / "src", self.runtime / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        env = {**os.environ, "HOME": str(self.fixture.root)}
        import sys
        before = self.fixture.manager().state_file.read_bytes()
        result = subprocess.run([sys.executable, "-I", str(PACKAGE / "hooks/router.py")], input=json.dumps(payload), capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertEqual(self.fixture.manager().state_file.read_bytes(), before)
        bad = subprocess.run([sys.executable, "-I", str(PACKAGE / "hooks/router.py")], input="{}", capture_output=True, text=True, env=env)
        self.assertEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()
