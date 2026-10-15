import json
import sqlite3
import unittest
import contextlib
import io
from unittest.mock import patch
from types import SimpleNamespace

import test_usage as fixtures
from tvlk_ai_router.config import RouterError
from tvlk_ai_router.history import report
from tvlk_ai_router.routing import record_route


class RoutingRecordTests(unittest.TestCase):
    record, meta, context, token, write = (fixtures.UsageTests.record, fixtures.UsageTests.meta, fixtures.UsageTests.context, fixtures.UsageTests.token, fixtures.UsageTests.write)
    tearDown = fixtures.UsageTests.tearDown

    def setUp(self):
        fixtures.UsageTests.setUp(self)
        config = {"coordinator": {"model": "gpt-6-luna", "reasoning_effort": "medium"},
                  "agents": {"coding": {"name": "tvlk_ai_route_coding", "model": "gpt-6.1-sol", "reasoning_effort": "medium"}}}
        self.manager = SimpleNamespace(home=self.home, data=self.home / "state", state={"status": "enabled"}, config=lambda: (b"", config))
        self.rows = [self.meta(), self.context(model="gpt-6-luna"), self.token(10)]
        self.write(self.rows)

    def save(self, category="coding", mode="delegated", reason="code_change", **kwargs):
        return record_route(self.manager, kwargs.pop("transcript", str(self.home / "sessions/a.jsonl")),
                            kwargs.pop("session_id", "root"), category, mode, reason, now=self.now)

    def result_report(self):
        return report(self.manager, now=self.now)

    def test_selection_and_actual_child_remain_separate(self):
        self.save()
        self.save()
        first = self.result_report()
        self.assertEqual(first["scope_comparison"]["nexus"]["execution_turns"], 1)
        r = first["routing_records"][0]
        self.assertEqual(len(r["route_decisions"]), 1)
        self.assertEqual(r["observed_models"], ["gpt-6-luna"])
        self.assertEqual(r["route_decisions"][0]["selected_model"], "gpt-6.1-sol")
        self.assertEqual(r["task_type"], "coding")
        self.assertEqual(r["activity"], "coordinator")
        child = self.context("child", "gpt-6-astra")
        child["payload"]["root_turn_id"] = "t"
        self.write([self.meta("child", agent_role="tvlk_ai_route_coding", source={"subagent": {"thread_spawn": {"parent_thread_id": "root"}}}, subagent_history_start_ordinal=1), child, self.token(3)], "child")
        result = self.result_report()
        c = next(r for r in result["routing_records"] if r["thread_id"] == "child")
        self.assertEqual(c["observed_models"], ["gpt-6-astra"])
        self.assertEqual(c["route_decisions"][0]["selected_model"], "gpt-6.1-sol")
        self.assertEqual(c["parent_turn_id"], "t")
        self.assertEqual(c["selection_scope"], "parent_turn")
        self.assertEqual(c["activity"], "executor")

    def test_direct_task_and_changed_intent_are_not_inferred_from_model(self):
        self.save(category="writing", mode="direct", reason="text_edit")
        first = self.result_report()
        self.assertEqual(first["routing_records"][0]["task_type"], "writing")
        self.assertEqual(first["routing_records"][0]["activity"], "direct")
        self.save(category="analysis", mode="direct", reason="complex_analysis")
        changed = self.result_report()
        self.assertEqual(changed["routing_records"][0]["task_type"], "mixed")
        self.assertEqual(changed["observed_tokens"], first["observed_tokens"])
        self.assertEqual(len(changed["routing_records"][0]["route_decisions"]), 2)

    def test_selection_without_usage_survives_source_removal(self):
        self.write(self.rows[:2])
        self.save()
        (self.home / "sessions/a.jsonl").unlink()
        result = self.result_report()
        self.assertEqual(result["turns_without_observed_events"], 1)
        self.assertEqual(result["estimate_status"], "partial")
        self.manager.state = None
        self.assertEqual(self.result_report()["routing_records"], result["routing_records"])

    def test_reject_bad_identity_completed_turn_subagent_and_symlinks(self):
        for options in ({"session_id": "other"}, {"reason": "private prompt"}, {"mode": "bad"}, {"category": "unknown"}):
            with self.assertRaises((RouterError, TypeError)):
                self.save(**options)
        outside = self.home / "outside.jsonl"
        outside.write_text("\n".join(json.dumps(r) for r in self.rows))
        with self.assertRaises(RouterError):
            self.save(transcript=str(outside))
        alias = self.home / "sessions/link.jsonl"
        alias.symlink_to(outside)
        with self.assertRaises(RouterError):
            self.save(transcript=str(alias))
        self.write(self.rows + [self.record("event_msg", {"type": "task_complete", "turn_id": "t"})])
        with self.assertRaises(RouterError):
            self.save()
        self.write([self.meta(agent_role="tvlk_ai_route_coding"), *self.rows[1:]])
        with self.assertRaises(RouterError):
            self.save()

    def test_no_prompt_or_transcript_path_retained_in_routes(self):
        self.write(self.rows + [self.record("response_item", {"role": "user", "content": "SECRET TASK TEXT"})])
        self.save(mode="direct")
        result = self.result_report()
        db = sqlite3.connect(result["history_file"])
        body = db.execute("SELECT body FROM routes").fetchone()[0]
        db.close()
        self.assertNotIn("SECRET TASK TEXT", body)
        self.assertNotIn(str(self.home), body)

    def test_cli_and_chat_report_and_record_paths(self):
        from tvlk_ai_router.cli import main
        with patch("tvlk_ai_router.cli.Manager", return_value=self.manager), patch("tvlk_ai_router.desktop.desktop_manager", return_value=self.manager):
            for prefix in ([], ["chat"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(prefix + ["record-route", "--transcript", str(self.home / "sessions/a.jsonl"), "--session-id", "root",
                                          "--category", "coding", "--mode", "direct", "--reason", "code_change"])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue())["status"], "recorded")
                for flags in ([], ["--json"]):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        code = main(prefix + ["review", "all", "--group-by", "task"] + flags)
                    self.assertEqual(code, 0)
                    if flags:
                        self.assertEqual(json.loads(output.getvalue())["scope_comparison"]["nexus"]["execution_turns"], 1)
                    else:
                        text = output.getvalue()
                        self.assertLess(text.index("Task types"), text.index("Models"))
                        self.assertIn("Daily usage (UTC)", text)
