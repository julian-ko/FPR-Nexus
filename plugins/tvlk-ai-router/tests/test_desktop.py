import contextlib
import io
import json
import os
import shutil
import tomllib
import tomlkit
from pathlib import Path
from unittest.mock import patch

import test_router
from tvlk_ai_router.config import RouterError
from tvlk_ai_router.desktop import (queue_request, perform_request, request_status,
                                   cancel_request, bootstrap, CHAT_HELP)
from tvlk_ai_router.storage import entry, inventory, load_snapshot, snapshot, transact


class DesktopTests(test_router.RouterTests):
    """Run new cases only; base fixture/helpers reuse the original suite."""

    def setUp(self):
        super().setUp()
        self.app = self.root / "Applications/TVLK-OpenAI-Router.app"
        self.app.mkdir(parents=True)
        (self.app / "fixture").write_text("old app")
        self.patches = [patch("tvlk_ai_router.desktop.installed_app", return_value=self.app),
                        patch("tvlk_ai_router.desktop.verify_app"),
                        patch("tvlk_ai_router.desktop.quiet_check"),
                        patch("tvlk_ai_router.desktop.subprocess.run")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        super().tearDown()

    def test_chat_request_is_deferred_until_gui_performs(self):
        self.install()
        before = inventory([self.home, self.shared, self.cfg])
        request = queue_request(self.manager(), "disable")
        self.assertEqual(request["status"], "pending")
        self.assertEqual(before, inventory([self.home, self.shared, self.cfg]))
        result = perform_request(self.manager(), request["id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.manager().state["status"], "disabled")
        self.assertTrue((self.manager().skill_dir / "SKILL.md").exists())

    def test_management_skill_survives_baseline_restore(self):
        first = self.install()["backup_id"]
        skill = self.manager().skill_dir / "SKILL.md"
        original = skill.read_bytes()
        request = queue_request(self.manager(), "restore", first)
        output = io.StringIO()
        with patch.dict(os.environ, {"TVLK_ROUTER_PROGRESS": "1"}), contextlib.redirect_stderr(output):
            perform_request(self.manager(), request["id"])
        stages = [json.loads(line.removeprefix("TVLK_PROGRESS "))["stage"] for line in output.getvalue().splitlines()]
        self.assertLess(stages.index("restore_preflight"), stages.index("snapshot_copy"))
        self.assertLess(stages.index("snapshot_copy"), stages.index("backup_verification"))
        self.assertEqual(skill.read_bytes(), original)
        self.assertEqual(self.manager().state["status"], "restored")

    def test_request_cannot_be_replaced_or_executed_after_cancel(self):
        self.install()
        request = queue_request(self.manager(), "disable")
        with self.assertRaises(RouterError):
            queue_request(self.manager(), "enable")
        cancel_request(self.manager())
        with self.assertRaises(RouterError):
            perform_request(self.manager(), request["id"])
        self.assertEqual(self.manager().state["status"], "enabled")

    def test_stale_request_does_not_apply_newer_config(self):
        self.install()
        request = queue_request(self.manager(), "apply")
        self.manager().source.write_text(self.manager().source.read_text() + "\n# subsequent edit\n")
        before = entry(self.home / "config.toml")
        with self.assertRaises(RouterError):
            perform_request(self.manager(), request["id"])
        self.assertEqual(before, entry(self.home / "config.toml"))

    def test_completed_request_does_not_reexecute(self):
        self.install()
        request = queue_request(self.manager(), "disable")
        perform_request(self.manager(), request["id"])
        count = len(self.manager().backups())
        perform_request(self.manager(), request["id"])
        self.assertEqual(count, len(self.manager().backups()))

    def test_window_launch_failure_is_not_reported_as_applied(self):
        self.install()
        with patch("tvlk_ai_router.desktop.subprocess.run", side_effect=OSError("launch failed")):
            with self.assertRaises(RouterError):
                queue_request(self.manager(), "disable")
        self.assertEqual(request_status(self.manager())["status"], "failed")
        self.assertEqual(self.manager().state["status"], "enabled")

    def test_bootstrap_rolls_back_app_copy_on_configuration_failure(self):
        source = self.root / "Downloaded.app"
        source.mkdir()
        (source / "fixture").write_text("new app")
        with patch("tvlk_ai_router.desktop.Manager.change", side_effect=RouterError("failure", 4)):
            with self.assertRaises(RouterError):
                bootstrap(str(source), self.manager())
        self.assertEqual((self.app / "fixture").read_text(), "old app")

    def test_bootstrap_installs_defaults_app_and_management_skill(self):
        source = self.root / "Downloaded.app"
        source.mkdir()
        (source / "fixture").write_text("new app")
        self.cfg.mkdir()
        self.manager().source.write_bytes(self.input.read_bytes())
        result = bootstrap(str(source), self.manager())
        self.assertEqual(result["status"], "installed")
        self.assertEqual((self.app / "fixture").read_text(), "new app")
        self.assertEqual(result["defaults"]["coordinator"], {"model": "gpt-6-luna", "reasoning_effort": "medium"})
        self.assertEqual(result["defaults"]["agents"]["analysis"]["reasoning_effort"], "xhigh")
        self.assertTrue((self.manager().skill_dir / "SKILL.md").exists())

    def test_chat_help_needs_no_installed_config(self):
        from tvlk_ai_router.cli import main
        output = io.StringIO()
        with patch("tvlk_ai_router.desktop.desktop_manager", side_effect=AssertionError("must not load user state")), contextlib.redirect_stdout(output):
            self.assertEqual(main(["chat", "help"]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value, CHAT_HELP)

    def test_progress_is_opt_in_reports_real_work_and_never_completes_failure(self):
        from tvlk_ai_router.progress import progress
        output = io.StringIO()
        with patch.dict(os.environ, {"TVLK_ROUTER_PROGRESS": "0"}), contextlib.redirect_stderr(output):
            progress("preflight", "Checking")
        self.assertEqual(output.getvalue(), "")
        source = self.root / "Downloaded.app"
        source.mkdir()
        (source / "fixture").write_text("new app")
        self.cfg.mkdir()
        self.manager().source.write_bytes(self.input.read_bytes())
        with patch.dict(os.environ, {"TVLK_ROUTER_PROGRESS": "1"}), contextlib.redirect_stderr(output):
            bootstrap(str(source), self.manager())
        events = [json.loads(line.removeprefix("TVLK_PROGRESS ")) for line in output.getvalue().splitlines()]
        stages = [event["stage"] for event in events]
        self.assertLess(stages.index("snapshot_copy"), stages.index("apply_transaction"))
        self.assertLess(stages.index("apply_transaction"), stages.index("complete"))
        self.assertTrue(any(event["stage"] == "copy_app" and event.get("completed") == event.get("total") == len(b"new app") and event.get("unit") == "bytes" for event in events))
        copied = [event for event in events if event["stage"] == "snapshot_copy"][-1]
        backup = load_snapshot(self.backups, self.manager().state["baseline"])
        sizes = {entry["sha256"]: entry["size"] for entry in backup["entries"].values() if entry["type"] == "file"}
        expected_bytes = backup["bytes"] * 2 + sum(sizes.values())
        self.assertEqual(copied["completed"], expected_bytes)
        self.assertEqual(copied["total"], expected_bytes)
        output = io.StringIO()
        with patch.dict(os.environ, {"TVLK_ROUTER_PROGRESS": "1"}), contextlib.redirect_stderr(output), patch("tvlk_ai_router.desktop.Manager.change", side_effect=RouterError("failure", 4)):
            with self.assertRaises(RouterError):
                bootstrap(str(source), self.manager())
        self.assertNotIn('"stage": "complete"', output.getvalue())

    def test_installer_migrates_only_unchanged_legacy_text_after_backup(self):
        doc = tomlkit.parse(self.input.read_text())
        original_description = "实现代码、常规排错、重构与测试。"
        original_instructions = "交付范围内的代码修改和适当验证。先定位问题；复杂根因或重复失败时返回具体证据供协调者升级。"
        doc["agents"]["coding"]["description"] = original_description
        doc["agents"]["coding"]["instructions"] = original_instructions
        doc["agents"]["writing"]["description"] = "Custom wording to preserve"
        doc["routing"]["rules"] = "Custom routing policy"
        doc["coordinator"]["reasoning_effort"] = "high"
        doc["agents"]["coding"]["reasoning_effort"] = "high"
        legacy = ("# preserve this comment\n" + tomlkit.dumps(doc)).encode()
        self.input.write_bytes(legacy)
        self.install()
        baseline_id = self.manager().state["baseline"]
        baseline_before = (self.backups / baseline_id / "manifest.json").read_bytes()
        # Ordinary apply does not migrate user text.
        self.manager().change("apply")
        self.assertEqual(self.manager().source.read_bytes(), legacy)
        source = self.root / "Downloaded.app"
        source.mkdir()
        (source / "fixture").write_text("new app")
        result = bootstrap(str(source), self.manager())
        current = self.manager().source.read_bytes()
        updated = tomllib.loads(current.decode())
        self.assertNotEqual(updated["agents"]["coding"]["description"], original_description)
        self.assertNotEqual(updated["agents"]["coding"]["instructions"], original_instructions)
        self.assertEqual(updated["agents"]["writing"]["description"], "Custom wording to preserve")
        self.assertEqual(updated["routing"]["rules"], "Custom routing policy")
        self.assertIn(b"# preserve this comment", current)
        for role in ("coordinator", "coding", "writing", "product", "analysis"):
            before = doc[role] if role == "coordinator" else doc["agents"][role]
            after = updated[role] if role == "coordinator" else updated["agents"][role]
            self.assertEqual((before["model"], before["reasoning_effort"]), (after["model"], after["reasoning_effort"]))
        backup = load_snapshot(self.backups, result["configuration"]["backup_id"])
        source_entry = backup["entries"][str(self.manager().source)]
        self.assertEqual((self.backups / backup["id"] / "files" / source_entry["sha256"]).read_bytes(), legacy)
        self.assertEqual(self.manager().state["baseline"], baseline_id)
        self.assertEqual((self.backups / baseline_id / "manifest.json").read_bytes(), baseline_before)

    def test_large_file_reports_intermediate_byte_progress_with_exact_totals(self):
        import itertools
        size = 6 * 1024 * 1024
        large = self.root / "large"
        large.write_bytes(b"x" * size)
        output = io.StringIO()
        ticks = itertools.count()
        with patch.dict(os.environ, {"TVLK_ROUTER_PROGRESS": "1"}), contextlib.redirect_stderr(output), patch("tvlk_ai_router.progress.time.monotonic", side_effect=lambda: next(ticks)):
            manifest = snapshot(self.backups, [large], "fixture", None, self.home)
        events = [json.loads(line.removeprefix("TVLK_PROGRESS ")) for line in output.getvalue().splitlines()]
        for stage, total in (("inventory", size), ("snapshot_copy", size * 3),
                             ("snapshot_verification", size), ("backup_verification", size)):
            values = [event for event in events if event["stage"] == stage and "completed" in event]
            self.assertTrue(any(0 < event["completed"] < total for event in values), stage)
            self.assertTrue(all(event["unit"] == "bytes" and event["total"] == total for event in values))
            self.assertEqual([event["completed"] for event in values], sorted(event["completed"] for event in values))
            self.assertEqual(values[-1]["completed"], total)
        self.assertEqual(entry(large)["sha256"], manifest["entries"][str(large)]["sha256"])
        target = self.root / "restored"
        target.write_bytes(b"old")
        output = io.StringIO()
        with patch.dict(os.environ, {"TVLK_ROUTER_PROGRESS": "1"}), contextlib.redirect_stderr(output), patch("tvlk_ai_router.progress.time.monotonic", side_effect=lambda: next(ticks)):
            transact(self.data, {target: (manifest["entries"][str(large)], self.backups / manifest["id"] / "files")})
        values = [json.loads(line.removeprefix("TVLK_PROGRESS ")) for line in output.getvalue().splitlines()]
        applied = [event for event in values if event["stage"] == "apply_transaction"]
        total = size * 3 + len(b"old")
        self.assertTrue(any(0 < event["completed"] < total for event in applied))
        self.assertTrue(all(event["total"] == total and event["unit"] == "bytes" for event in applied))
        self.assertEqual(applied[-1]["completed"], total)
        self.assertEqual(entry(target)["sha256"], entry(large)["sha256"])
        source = self.root / "Downloaded.app"
        source.mkdir()
        shutil.copy2(large, source / "fixture")
        self.cfg.mkdir()
        self.manager().source.write_bytes(self.input.read_bytes())
        output = io.StringIO()
        with patch.dict(os.environ, {"TVLK_ROUTER_PROGRESS": "1"}), contextlib.redirect_stderr(output), patch("tvlk_ai_router.progress.time.monotonic", side_effect=lambda: next(ticks)):
            bootstrap(str(source), self.manager())
        values = [json.loads(line.removeprefix("TVLK_PROGRESS ")) for line in output.getvalue().splitlines()]
        copied = [event for event in values if event["stage"] == "copy_app"]
        self.assertTrue(any(0 < event["completed"] < size for event in copied))
        self.assertTrue(all(event["total"] == size and event["unit"] == "bytes" for event in copied))
        self.assertEqual(copied[-1]["completed"], size)
        self.assertEqual(entry(self.app / "fixture")["sha256"], entry(large)["sha256"])


# unittest includes inherited test methods. Keep the shared fixture without
# rerunning those identical cases under the patched desktop environment.
for _name in list(vars(test_router.RouterTests)):
    if _name.startswith("test_") and _name not in vars(DesktopTests):
        setattr(DesktopTests, _name, None)
