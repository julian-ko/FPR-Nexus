import contextlib
import copy
import io
import json
import os
import tempfile
import tomllib
import unittest
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

from tvlk_ai_router.cli import main
from tvlk_ai_router.config import (RouterError, parse, native_agents, routing_block,
                                   merge_keys, get_keys, desired_keys, digest, json_bytes, model_check)
from tvlk_ai_router.manager import Manager
from tvlk_ai_router.storage import inventory, entry, transact, recover, load_snapshot


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tvlk-router-test-")
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "codex"
        self.home.mkdir()
        self.cfg = self.root / "config"
        self.data = self.root / "data"
        self.shared = self.root / "agents"
        self.backups = self.data / "backups"
        self.input = self.root / "input.toml"
        raw = files("tvlk_ai_router").joinpath("data/router.example.toml").read_text()
        raw = raw.replace("~/.local/share/tvlk-ai-router/backups", str(self.backups))
        self.input.write_text(raw)
        self.original = b'# keep this comment\nmodel = "existing-model"\nmodel_reasoning_effort = "high"\n\n[mcp_servers.demo]\ncommand = "demo"\n'
        (self.home / "config.toml").write_bytes(self.original)
        (self.home / "AGENTS.md").write_text("# User rules\nOnly explicit /plan doc invokes that skill.\n")
        models = [{"slug": name, "visibility": "list", "supported_reasoning_levels": [{"effort": e} for e in ["low", "medium", "high", "xhigh"]]}
                  for name in ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"]]
        (self.home / "models_cache.json").write_text(json.dumps({"client_version": "fixture", "models": models}))

    def tearDown(self):
        self.tmp.cleanup()

    def manager(self):
        return Manager(str(self.home), str(self.cfg), str(self.data), str(self.shared))

    def install(self):
        return self.manager().change("install", str(self.input))

    def test_install_time_survives_apply_disable_restore_and_legacy_upgrade(self):
        result = self.install()
        installed = self.manager().state["installed_at"]
        self.manager().change("disable")
        self.assertEqual(self.manager().state["installed_at"], installed)
        self.manager().change("enable")
        self.manager().restore(result["backup_id"])
        self.assertEqual(self.manager().state["installed_at"], installed)
        self.manager().change("enable", str(self.input))
        m = self.manager()
        state = dict(m.state)
        state.pop("installed_at")
        m.state_file.write_bytes(json_bytes(state))
        m = self.manager()
        m.change("disable")
        m.change("enable")
        self.assertNotIn("installed_at", self.manager().state)
        code, out, err = self.cli("review", "--json")
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["installation_start"]["approximate"])

    def cli(self, *argv):
        args = ["--codex-home", str(self.home), "--config-dir", str(self.cfg),
                "--data-dir", str(self.data), "--agents-home", str(self.shared), *argv]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), patch("tvlk_ai_router.cli.quiet_check"):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_generated_agents_and_rules(self):
        d = parse(self.input.read_bytes())
        agents = native_agents(d)
        self.assertEqual(len(agents), 4)
        for role, a in d["agents"].items():
            v = tomllib.loads(agents[a["name"] + ".toml"].decode())
            self.assertEqual(v["model"], a["model"])
            self.assertEqual(v["model_reasoning_effort"], a["reasoning_effort"])
            self.assertFalse(v["agents"]["enabled"])
            self.assertIn(a["name"], routing_block(d))

    def test_model_availability_preflight(self):
        d = parse(self.input.read_bytes())
        self.assertEqual(d["agents"]["coding"]["model"], "gpt-6.1-sol")
        self.assertEqual(model_check(self.home, d)["status"], "cache_matched")
        old = copy.deepcopy(d)
        old["agents"]["coding"]["model"] = "gpt-6-sol"
        with self.assertRaisesRegex(RouterError, "Model unavailable"):
            model_check(self.home, old)
        unsupported = copy.deepcopy(d)
        unsupported["agents"]["coding"]["reasoning_effort"] = "ultra"
        with self.assertRaisesRegex(RouterError, "Reasoning effort unsupported"):
            model_check(self.home, unsupported)
        cache = self.home / "models_cache.json"
        payload = json.loads(cache.read_bytes())
        for visibility in ("hide", "hidden"):
            with self.subTest(visibility=visibility):
                payload["models"][1]["visibility"] = visibility
                cache.write_text(json.dumps(payload))
                with self.assertRaisesRegex(RouterError, "Model unavailable"):
                    model_check(self.home, d)

    def test_strict_schema(self):
        for old, new in [('reasoning_effort = "medium"', 'reasoning_effrot = "medium"'),
                         ('max_active_executors = 1', 'max_active_executors = 2'),
                         ('name = "tvlk_ai_route_coding"', 'name = "../../bad"')]:
            with self.subTest(new=new), self.assertRaises(RouterError):
                parse(self.input.read_bytes().replace(old.encode(), new.encode(), 1))

    def test_dry_run_has_no_writes(self):
        before = inventory([self.root])
        result = self.manager().change("install", str(self.input), dry=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(before, inventory([self.root]))

    def test_install_backup_and_help(self):
        code, out, err = self.cli("install", "--config", str(self.input))
        self.assertEqual(code, 0, err)
        self.assertIn("tvlk-ai-router disable", out)
        self.assertIn("gpt-6.1-sol", out)
        m = self.manager()
        self.assertEqual(m.state["status"], "enabled")
        backup = load_snapshot(self.backups, m.state["baseline"])
        before = backup["entries"][str(self.home / "config.toml")]["sha256"]
        self.assertEqual(before, digest(self.original))
        self.assertIn("Only explicit /plan doc", (self.home / "AGENTS.md").read_text())
        self.assertEqual(m.show()["runtime"], "unverified")

    def test_backup_publishes_before_sealing_directory(self):
        real_rename = os.rename
        def rename_writable(source, target):
            source = Path(source)
            if source.name.endswith(".partial") and not source.stat().st_mode & 0o200:
                raise PermissionError(13, "Read-only source directory", str(source))
            return real_rename(source, target)
        with patch("tvlk_ai_router.storage.os.rename", side_effect=rename_writable):
            result = self.install()
        backup = self.backups / result["backup_id"]
        self.assertEqual(backup.stat().st_mode & 0o777, 0o500)
        self.assertEqual((backup / "files").stat().st_mode & 0o777, 0o500)
        for path in backup.rglob("*"):
            if path.is_file():
                self.assertEqual(path.stat().st_mode & 0o777, 0o400)
        load_snapshot(self.backups, result["backup_id"], verify=True)

    def test_backup_rename_denied_preserves_partial_and_configuration(self):
        original = inventory([self.home, self.cfg, self.shared])
        with patch("tvlk_ai_router.storage.os.rename", side_effect=PermissionError(13, "Permission denied")):
            with self.assertRaisesRegex(RouterError, "unfinished backup is preserved"):
                self.install()
        self.assertEqual(inventory([self.home, self.cfg, self.shared]), original)
        self.assertFalse(self.manager().state_file.exists())
        partials = list(self.backups.glob("*.partial"))
        self.assertEqual(len(partials), 1)
        retained = inventory(partials)
        self.assertFalse(any(item["verified"] for item in self.manager().backups()))
        result = self.install()
        self.assertEqual(inventory(partials), retained)
        load_snapshot(self.backups, result["backup_id"], verify=True)

    def test_repeat_operations_are_idempotent(self):
        self.install()
        n = len(self.manager().backups())
        self.manager().change("install", str(self.input))
        self.manager().change("apply")
        self.assertEqual(n, len(self.manager().backups()))
        self.manager().change("disable")
        n = len(self.manager().backups())
        self.manager().change("disable")
        self.assertEqual(n, len(self.manager().backups()))

    def test_apply_changes_one_agent_only(self):
        self.install()
        m = self.manager()
        original_hashes = dict(m.state["agent_hashes"])
        raw = m.source.read_text().replace('reasoning_effort = "low"', 'reasoning_effort = "high"')
        m.source.write_text(raw)
        m.change("apply")
        changed = [p for p, sha in original_hashes.items() if m.state["agent_hashes"][p] != sha]
        self.assertEqual(changed, [str(self.home / "agents/tvlk_ai_route_writing.toml")])

    def test_disable_exact_original_and_no_deletion_of_unrelated(self):
        self.install()
        path = self.home / "config.toml"
        path.write_text(path.read_text() + '\n[mcp_servers.new]\ncommand = "new"\n')
        self.manager().change("disable")
        d = tomllib.loads(path.read_text())
        self.assertEqual(d["model"], "existing-model")
        self.assertIn("new", d["mcp_servers"])
        self.assertIn("# keep this comment", path.read_text())
        self.assertNotIn("BEGIN TVLK", (self.home / "AGENTS.md").read_text())

    def test_disable_restores_original_bytes_without_unrelated_changes(self):
        self.install()
        self.manager().change("disable")
        self.assertEqual((self.home / "config.toml").read_bytes(), self.original)

    def test_new_enable_uses_new_baseline(self):
        self.install()
        self.manager().change("disable")
        path = self.home / "config.toml"
        path.write_text(path.read_text().replace("existing-model", "new-personal-model"))
        self.manager().change("enable")
        self.manager().change("disable")
        self.assertEqual(tomllib.loads(path.read_text())["model"], "new-personal-model")

    def test_drift_stops_entire_change(self):
        self.install()
        p = self.home / "agents/tvlk_ai_route_coding.toml"
        p.write_text(p.read_text() + "\n# manual\n")
        before = inventory([self.root])
        with self.assertRaises(RouterError):
            self.manager().change("disable")
        self.assertEqual(before, inventory([self.root]))

    def test_restore_and_switch_back_preserves_snapshots(self):
        first = self.install()["backup_id"]
        immutable = inventory([self.backups / first])
        active = (self.home / "config.toml").read_bytes()
        (self.home / "new.config.toml").write_text('model="later"\n')
        self.home.joinpath("sessions").mkdir()
        self.home.joinpath("sessions/current.jsonl").write_text("history after install")
        result = self.manager().restore(first)
        self.assertEqual((self.home / "config.toml").read_bytes(), self.original)
        self.assertFalse((self.home / "new.config.toml").exists())
        self.assertEqual((self.home / "sessions/current.jsonl").read_text(), "history after install")
        self.manager().restore(result["pre_restore_backup"])
        self.assertEqual((self.home / "config.toml").read_bytes(), active)
        self.assertTrue((self.home / "new.config.toml").exists())
        self.assertEqual(immutable, inventory([self.backups / first]))

    def test_mixed_preferences_preserve_threads_and_full_scope_is_explicit(self):
        p = self.home / ".codex-global-state.json"
        p.write_text(json.dumps({"electron-main-window-bounds": {"x": 1}, "thread-project-assignments": {"a": "old"}}))
        first = self.install()["backup_id"]
        p.write_text(json.dumps({"electron-main-window-bounds": {"x": 2}, "thread-project-assignments": {"a": "new"}}))
        self.manager().restore(first)
        value = json.loads(p.read_text())
        self.assertEqual(value["electron-main-window-bounds"], {"x": 1})
        self.assertEqual(value["thread-project-assignments"], {"a": "new"})
        self.manager().restore(first, scope="full")
        self.assertEqual(json.loads(p.read_text())["thread-project-assignments"], {"a": "old"})

    def test_backup_tampering_is_rejected(self):
        first = self.install()["backup_id"]
        manifest = self.backups / first / "manifest.json"
        manifest.chmod(0o600)
        manifest.write_bytes(manifest.read_bytes() + b" ")
        before = (self.home / "config.toml").read_bytes()
        with self.assertRaises(RouterError):
            self.manager().restore(first)
        self.assertEqual(before, (self.home / "config.toml").read_bytes())

    def test_restore_readonly_configuration_directory(self):
        plugins = self.home / "plugins"
        plugins.mkdir()
        resource = plugins / "settings.json"
        resource.write_text('{"setting":"old"}')
        resource.chmod(0o400)
        plugins.chmod(0o500)
        first = self.install()["backup_id"]
        plugins.chmod(0o700)
        resource.chmod(0o600)
        resource.write_text('{"setting":"new"}')
        self.manager().restore(first)
        self.assertEqual(resource.read_text(), '{"setting":"old"}')
        self.assertEqual(plugins.stat().st_mode & 0o777, 0o500)
        self.assertEqual(resource.stat().st_mode & 0o777, 0o400)

    def test_restore_into_existing_readonly_directory(self):
        directory = self.root / "readonly"
        directory.mkdir()
        target = directory / "config"
        target.write_bytes(b"old")
        directory.chmod(0o500)
        self.data.mkdir()
        transact(self.data, {target: b"new"})
        self.assertEqual(target.read_bytes(), b"new")
        self.assertEqual(directory.stat().st_mode & 0o777, 0o500)

    def test_sqlite_maintenance_lock_is_runtime_backed_up_and_preserved(self):
        maintenance = self.home / ".sqlite-maintenance.lock"
        maintenance.write_bytes(b"baseline lock data")
        original_inode = maintenance.stat().st_ino
        m = self.manager()
        roots = [self.home, self.shared, self.cfg]
        self.assertEqual(m.classify(maintenance, roots), "runtime")
        self.assertEqual(m.classify(self.home / "other.lock", roots), "preserved")
        self.assertEqual(m.classify(self.home / "custom" / maintenance.name, roots), "preserved")
        first = self.install()["backup_id"]
        self.assertEqual(maintenance.read_bytes(), b"baseline lock data")
        self.assertEqual(maintenance.stat().st_ino, original_inode)
        snapshot = load_snapshot(self.backups, first)
        saved = snapshot["entries"][str(maintenance)]
        self.assertEqual(saved["type"], "file")
        self.assertEqual((self.backups / first / "files" / saved["sha256"]).read_bytes(), b"baseline lock data")
        maintenance.write_bytes(b"current lock data")
        restored = self.manager().restore(first)
        self.assertNotIn(str(maintenance), restored["changes"])
        self.assertEqual(maintenance.read_bytes(), b"current lock data")
        self.assertEqual(maintenance.stat().st_ino, original_inode)
        maintenance.unlink()
        self.manager().restore(first)
        self.assertFalse(maintenance.exists())
        unknown = self.home / "other.lock"
        unknown.write_bytes(b"unclassified data")
        self.manager().restore(first)
        self.assertEqual(unknown.read_bytes(), b"unclassified data")

    def test_new_runtime_directories_are_backed_up_and_config_restore_preserves_them(self):
        names = ("claude-cowork-transcript-imports", "project-metadata-locks", "archived_sessions",
                 "app-server-control", "app-server-daemon", "macos", "tui-thread-preference-capabilities")
        runtime_files = []
        m = self.manager()
        roots = [self.home, self.cfg, self.shared]
        for name in names:
            directory = self.home / name
            child = directory / "nested" / "runtime.bin"
            child.parent.mkdir(parents=True)
            child.write_bytes(b"before install")
            runtime_files.append(child)
            expected = "runtime" if name in names[:3] else "preserved"
            self.assertEqual(m.classify(directory, roots), expected)
            self.assertEqual(m.classify(child, roots), expected)
            self.assertEqual(m.classify(self.home / "custom" / name, roots), "preserved")
            self.assertEqual(m.classify(self.home / (name + "-custom"), roots), "preserved")
        first = self.install()["backup_id"]
        manifest = load_snapshot(self.backups, first)
        for child in runtime_files:
            saved = manifest["entries"][str(child)]
            self.assertEqual((self.backups / first / "files" / saved["sha256"]).read_bytes(), b"before install")
            child.write_bytes(b"current runtime")
        result = self.manager().restore(first)
        for child in runtime_files:
            self.assertNotIn(str(child), result["changes"])
            self.assertEqual(child.read_bytes(), b"current runtime")
        import shutil
        for name in names:
            shutil.rmtree(self.home / name)
        self.manager().restore(first)
        for name in names:
            self.assertFalse((self.home / name).exists())
        unrelated = self.home / "custom" / names[0]
        unrelated.mkdir(parents=True)
        self.manager().restore(first)
        self.assertTrue(unrelated.is_dir())

    def test_timestamped_config_copy_is_backed_up_and_preserved(self):
        saved_copy = self.home / "config.toml.before-tvlk-1.0.4-20261014-102443"
        saved_copy.write_bytes(self.original)
        first = self.install()["backup_id"]
        saved = load_snapshot(self.backups, first)["entries"][str(saved_copy)]
        self.assertEqual((self.backups / first / "files" / saved["sha256"]).read_bytes(), self.original)
        newer_copy = self.home / "config.toml.before-tvlk-1.0.5-20261014-112443"
        newer_copy.write_bytes(b"later backup")
        self.manager().restore(first)
        self.assertEqual(saved_copy.read_bytes(), self.original)
        self.assertEqual(newer_copy.read_bytes(), b"later backup")
        for name in ("config.toml.before-tvlk-custom", saved_copy.name + "-custom"):
            self.assertEqual(self.manager().classify(self.home / name, [self.home]), "preserved")

    def test_client_state_socket_is_recorded_and_preserved(self):
        import socket
        directory = self.home / "app-server-control"
        directory.mkdir()
        path = directory / "control.sock"
        with socket.socket(socket.AF_UNIX) as sock:
            cwd = Path.cwd()
            try:
                os.chdir(directory)
                sock.bind(path.name)
            finally:
                os.chdir(cwd)
            first = self.install()["backup_id"]
            self.assertEqual(load_snapshot(self.backups, first)["entries"][str(path)]["type"], "special")
            self.manager().restore(first)
            self.assertTrue(path.is_socket())

    def test_unfamiliar_content_survives_install_validate_and_config_restore(self):
        names = ("packages", "tui-thread-reference-capabilities", "future-client-data")
        for name in names:
            directory = self.home / name
            directory.mkdir()
            (directory / "data.bin").write_bytes(b"original bytes")
        opaque = self.home / "unrelated.toml"
        opaque.write_bytes(b"not a TOML configuration [")
        link = self.home / "future-client-link"
        link.symlink_to(self.root / "missing-target")
        before = inventory([self.home / n for n in names] + [opaque, link])
        result = self.install()
        self.assertEqual(before, inventory([self.home / n for n in names] + [opaque, link]))
        saved = load_snapshot(self.backups, result["backup_id"])
        for path, entry_data in before.items():
            self.assertEqual(saved["entries"][path], entry_data)
        self.assertIn(str(self.home / names[0]), result["preserved_paths"])
        code, out, err = self.cli("config", "validate", "--json")
        self.assertEqual(code, 0, err)
        self.assertIn(str(opaque), json.loads(out)["preserved_paths"])
        changed = self.home / names[0] / "data.bin"
        changed.write_bytes(b"new bytes")
        later = self.home / "future-added-after-install"
        later.write_bytes(b"keep later data")
        self.manager().change("disable")
        self.manager().change("enable")
        self.manager().restore(result["backup_id"])
        self.assertEqual(changed.read_bytes(), b"new bytes")
        self.assertEqual(later.read_bytes(), b"keep later data")
        self.assertTrue(link.is_symlink())
        self.manager().restore(result["backup_id"], scope="full")
        self.assertEqual(changed.read_bytes(), b"original bytes")
        self.assertFalse(later.exists())

    def test_unreadable_preserved_content_still_blocks_writes(self):
        blocked = self.home / "future-client-file"
        blocked.write_bytes(b"must be backed up")
        original_open = Path.open
        def checked_open(path, *args, **kwargs):
            if path == blocked:
                raise PermissionError("fixture read denied")
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", checked_open):
            with self.assertRaises(PermissionError):
                self.install()
        self.assertEqual((self.home / "config.toml").read_bytes(), self.original)
        self.assertFalse(self.manager().state_file.exists())

    def test_explicit_configuration_path_remains_restorable(self):
        unknown = self.home / "custom.setting"
        unknown.write_text("user configuration")
        self.input.write_text(self.input.read_text().replace("additional_config_paths = []", 'additional_config_paths = ["' + str(unknown) + '"]'))
        first = self.install()["backup_id"]
        unknown.write_text("changed")
        self.manager().restore(first)
        self.assertEqual(unknown.read_text(), "user configuration")

    def test_symlink_managed_target_is_rejected(self):
        p = self.home / "config.toml"
        p.unlink()
        p.symlink_to(self.input)
        with self.assertRaises(RouterError):
            self.install()

    def test_external_config_and_symlink_resources_are_backed_up(self):
        external = self.root / "external.toml"
        external.write_text('name = "external"\n')
        path = self.home / "config.toml"
        path.write_text(path.read_text() + '\n[agents.existing]\nconfig_file = "' + str(external) + '"\n')
        target = self.root / "external-skills"
        target.mkdir()
        (target / "SKILL.md").write_text("User-owned skill")
        self.shared.mkdir()
        (self.shared / "linked").symlink_to(target)
        result = self.install()
        manifest = load_snapshot(self.backups, result["backup_id"])
        self.assertIn(str(external), manifest["entries"])
        self.assertIn(str(target / "SKILL.md"), manifest["entries"])

    def test_plugin_cache_links_are_backed_up_without_following_or_config_restore(self):
        cache = self.home / "plugins/cache/context-mode/context-mode/1.0.169"
        binaries = cache / "node_modules/.bin"
        binaries.mkdir(parents=True)
        broken = binaries / "node-which"
        broken.symlink_to("../which/bin/node-which")
        loop = binaries / "cycle"
        loop.symlink_to("cycle")
        external = self.root / "external-package"
        external.mkdir()
        (external / "data").write_bytes(b"not a configuration dependency")
        (binaries / "valid").symlink_to(external)
        cached = cache / "program.py"
        cached.write_bytes(b"before")
        first = self.install()["backup_id"]
        snapshot = load_snapshot(self.backups, first)
        self.assertEqual(snapshot["entries"][str(broken)]["target"], "../which/bin/node-which")
        self.assertEqual(snapshot["entries"][str(loop)]["type"], "link")
        self.assertNotIn(str(external / "data"), snapshot["entries"])
        cached.write_bytes(b"new client cache")
        self.manager().restore(first)
        self.assertEqual(cached.read_bytes(), b"new client cache")
        self.assertTrue(broken.is_symlink())
        self.assertEqual(self.manager().classify(self.home / "plugins/settings.json", [self.home]), "config")

    def test_incidental_skill_links_are_preserved_but_explicit_missing_targets_block(self):
        target = self.root / "external-skills"
        target.mkdir()
        (target / "SKILL.md").write_text("A linked skill")
        (target / "broken-dependency").symlink_to("missing")
        (target / "cycle").symlink_to("cycle")
        self.shared.mkdir()
        (self.shared / "linked").symlink_to(target)
        first = self.install()["backup_id"]
        snapshot = load_snapshot(self.backups, first)
        self.assertEqual(snapshot["entries"][str(target / "broken-dependency")]["type"], "link")
        self.assertEqual(snapshot["entries"][str(target / "cycle")]["type"], "link")
        d = parse(self.input.read_bytes())
        d["backup"]["additional_config_paths"] = [str(target / "broken-dependency")]
        with self.assertRaisesRegex(RouterError, "target does not exist"):
            self.manager().roots(d)
        config = self.home / "config.toml"
        config.write_text(config.read_text() + '\n[agents.explicit]\nconfig_file = "' + str(target / "broken-dependency") + '"\n')
        with self.assertRaisesRegex(RouterError, "reference does not exist"):
            self.manager().roots(parse(self.input.read_bytes()))

    def test_empty_original_config_is_restored_to_absent(self):
        (self.home / "config.toml").unlink()
        (self.home / "AGENTS.md").unlink()
        self.install()
        self.manager().change("disable")
        self.assertFalse((self.home / "config.toml").exists())
        self.assertFalse((self.home / "AGENTS.md").exists())

    def test_backup_cannot_be_nested_in_codex_home(self):
        self.input.write_text(self.input.read_text().replace(str(self.backups), str(self.home / "backups")))
        with self.assertRaises(RouterError):
            self.install()

    def test_codex_process_blocks_write_commands(self):
        from tvlk_ai_router.storage import quiet_check
        from subprocess import CompletedProcess
        with patch("tvlk_ai_router.storage.subprocess.run", return_value=CompletedProcess([], 0, "12345 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n", "")):
            with self.assertRaises(RouterError) as err:
                quiet_check()
        self.assertEqual(err.exception.code, 4)

    def test_missing_model_does_not_install(self):
        p = self.home / "models_cache.json"
        p.unlink()
        before = inventory([self.root])
        with self.assertRaises(RouterError) as err:
            self.install()
        self.assertEqual(err.exception.code, 3)
        self.assertEqual(before, inventory([self.root]))

    def test_non_default_home_cannot_be_retargeted(self):
        self.install()
        with self.assertRaises(RouterError):
            Manager(str(self.root / "other"), str(self.cfg), str(self.data), str(self.shared))

    def test_disable_works_with_invalid_edited_source_and_missing_model_cache(self):
        self.install()
        self.manager().source.write_text("not valid TOML = [")
        (self.home / "models_cache.json").unlink()
        self.manager().change("disable")
        self.assertEqual((self.home / "config.toml").read_bytes(), self.original)

    def test_change_between_plan_and_backup_is_not_overwritten(self):
        m = self.manager()
        original_report = m.report
        def changed_report(*args, **kwargs):
            path = self.home / "config.toml"
            path.write_bytes(self.original + b"\n# concurrent edit\n")
            return original_report(*args, **kwargs)
        with patch.object(m, "report", side_effect=changed_report):
            with self.assertRaises(RouterError):
                m.change("install", str(self.input))
        self.assertIn(b"concurrent edit", (self.home / "config.toml").read_bytes())
        self.assertFalse(m.state_file.exists())

    def test_override_and_agent_name_collision(self):
        override = self.home / "AGENTS.override.md"
        override.write_text("Override rules\n")
        self.install()
        self.assertIn("BEGIN TVLK", override.read_text())
        self.assertNotIn("BEGIN TVLK", (self.home / "AGENTS.md").read_text())

    def test_backup_failure_does_not_change_config(self):
        with patch("tvlk_ai_router.manager.snapshot", side_effect=RouterError("copy failed", 5)):
            with self.assertRaises(RouterError):
                self.install()
        self.assertEqual((self.home / "config.toml").read_bytes(), self.original)
        self.assertFalse(self.manager().state_file.exists())

    def test_transaction_failure_rolls_back_created_and_existing_files(self):
        self.data.mkdir()
        a, b = self.root / "a", self.root / "nested" / "b"
        a.write_bytes(b"before")
        with self.assertRaises(RouterError) as err:
            transact(self.data, {a: b"after", b: b"created"}, fail_after=2)
        self.assertEqual(err.exception.code, 6)
        self.assertEqual(a.read_bytes(), b"before")
        self.assertFalse(b.exists())
        self.assertFalse(b.parent.exists())

    def test_crash_recovery_checks_conflicts(self):
        self.data.mkdir()
        a = self.root / "a"
        a.write_bytes(b"before")
        from tvlk_ai_router import storage
        original = storage.materialize
        def crash(path, value, blobs, on_bytes=None):
            original(path, value, blobs, on_bytes)
            raise KeyboardInterrupt()
        with patch("tvlk_ai_router.storage.materialize", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                transact(self.data, {a: b"after"})
        a.write_bytes(b"user changed after crash")
        with self.assertRaises(RouterError):
            recover(self.data)
        self.assertEqual(a.read_bytes(), b"user changed after crash")
        a.write_bytes(b"after")
        self.assertTrue(recover(self.data))
        self.assertEqual(a.read_bytes(), b"before")

    def test_cli_readonly_json_and_no_arguments(self):
        before = inventory([self.root])
        for args in [(), ("help",), ("config", "show", "--json"), ("backup", "list", "--json"),
                     ("config", "example"), ("install", "--config", str(self.input), "--dry-run")]:
            with self.subTest(args=args):
                code, out, err = self.cli(*args)
                self.assertEqual(code, 0, err)
        self.assertEqual(before, inventory([self.root]))


if __name__ == "__main__":
    unittest.main()
