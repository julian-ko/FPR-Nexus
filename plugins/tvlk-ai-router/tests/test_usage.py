import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tvlk_ai_router.usage import review, installation_start
from tvlk_ai_router.config import RouterError


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        (self.home / "sessions").mkdir()
        self.now = datetime(2026, 10, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, typ, payload, day="2026-10-11"):
        return {"timestamp": day + "T12:00:00Z", "type": typ, "payload": payload}

    def meta(self, ident="root", **extra):
        return self.record("session_meta", {"id": ident, "source": "vscode", **extra})

    def context(self, turn="t", model="sol"):
        return self.record("turn_context", {"turn_id": turn, "model": model, "effort": "medium"})

    def token(self, total, last=None):
        def value(n):
            return {"input_tokens": n, "output_tokens": n, "total_tokens": n * 2, "cached_input_tokens": 0, "reasoning_output_tokens": 0}
        return self.record("event_msg", {"type": "token_count", "info": {"total_token_usage": value(total), "last_token_usage": value(last if last is not None else total)}})

    def write(self, rows, name="a"):
        (self.home / "sessions" / (name + ".jsonl")).write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def result(self, **kw):
        return review(self.home, {}, now=self.now, **kw)

    def test_duplicate_cumulative_events_and_copies(self):
        rows = [self.meta(), self.context(), self.token(10), self.token(10), self.token(15, 5),
                self.record("event_msg", {"type": "task_complete", "turn_id": "t"})]
        self.write(rows)
        self.write(rows, "copy")
        result = self.result()
        self.assertEqual(result["execution_turns"], 1)
        self.assertEqual(result["observed_total_tokens"], 30)
        self.assertEqual(result["models"][0]["category"], "unknown")
        self.assertEqual(result["details"][0]["status"], "completed")

    def test_child_excludes_inherited_and_marks_parent(self):
        inherited = [self.meta("child", agent_role="tvlk_ai_route_coding", source={"subagent": {"thread_spawn": {"parent_thread_id": "root"}}}, subagent_history_start_ordinal=4),
                     self.meta(), self.context("parent"), self.token(10)]
        child = self.context("child")
        child["payload"]["root_turn_id"] = "t"
        self.write(inherited + [child, self.token(15, 5)], "child")
        self.write([self.meta(), self.context(), self.token(2)], "parent")
        result = self.result()
        self.assertEqual(result["execution_turns"], 2)
        self.assertEqual(result["observed_total_tokens"], 14)
        self.assertEqual({r["category"] for r in result["models"]}, {"coding", "coordinator"})

    def test_model_switch_reset_and_cancel(self):
        self.write([self.meta(), self.context(), self.token(10), self.context(model="astra"), self.token(20, 10),
                    self.token(25, 5), self.token(2), self.record("event_msg", {"type": "turn_aborted"})])
        result = self.result()
        self.assertEqual(result["execution_turns"], 1)
        self.assertEqual(result["observed_total_tokens"], 30)
        self.assertEqual(result["coverage"]["unknown_token_events"], 2)
        self.assertEqual({r["model"] for r in result["models"]}, {"sol", "astra"})
        self.assertEqual(result["details"][0]["status"], "cancelled")

    def test_missing_baseline_malformed_and_system(self):
        self.write([self.meta(), self.context(), self.token(10, 2)])
        with (self.home / "sessions/a.jsonl").open("a") as stream:
            stream.write('{"truncated":')
        self.write([self.meta("guard", source={"subagent": {"other": "guardian"}}), self.context(), self.token(100)], "guard")
        result = self.result()
        self.assertEqual(result["observed_total_tokens"], 0)
        self.assertEqual(result["coverage"]["malformed_lines"], 1)
        self.assertEqual(result["coverage"]["excluded_system_sessions"], 1)
        self.assertIsNone(result["details"][0]["tokens"]["total_tokens"])

    def test_timeframe_and_install_date(self):
        self.write([self.meta(), self.context(), self.token(10)])
        result = review(self.home, {"installed_at": "2026-10-11T18:00:00Z"}, "since-install", self.now)
        self.assertEqual(result["execution_turns"], 0)
        self.assertFalse(result["installation_start"]["approximate"])
        start = installation_start({"baseline": "20261006T072808Z-fa6fe7b8"})
        self.assertTrue(start["approximate"])
        self.assertEqual(start["source"], "legacy_baseline_backup")
        with self.assertRaises(RouterError):
            self.result(period="since-install")

    def test_missing_info_optional_fields_and_bad_schema(self):
        token = self.token(10)
        for field in ("cached_input_tokens", "reasoning_output_tokens"):
            for key in ("total_token_usage", "last_token_usage"):
                token["payload"]["info"][key].pop(field)
        self.write([self.meta(agent_role=None), self.context(), self.record("event_msg", {"type": "token_count", "info": None}), token])
        self.write([self.meta(["bad"]), self.context(model=None), self.token(100)], "bad")
        result = self.result()
        self.assertEqual(result["execution_turns"], 1)
        self.assertEqual(result["observed_total_tokens"], 20)
        self.assertEqual(result["details"][0]["token_coverage"], "partial")
        self.assertIsNone(result["models"][0]["tokens"]["cached_input_tokens"])
        self.assertIsNone(result["models"][0]["tokens"]["reasoning_output_tokens"])

    def test_missing_history_boundary_and_detail_limit(self):
        self.write([self.meta("child", source={"subagent": {"thread_spawn": {"parent_thread_id": "p"}}}), self.context(), self.token(50)], "child")
        rows = [self.meta()]
        for i in range(105):
            rows += [self.context(str(i)), self.token(i + 1, 1)]
        self.write(rows)
        result = self.result()
        self.assertEqual(result["execution_turns"], 105)
        self.assertEqual(len(result["details"]), 100)
        self.assertEqual(result["details_omitted"], 5)
        self.assertEqual(result["coverage"]["unknown_history_sessions"], 1)

    def test_same_counter_after_reset_is_new_usage(self):
        self.write([self.meta(), self.context(), self.token(10), self.token(2), self.token(10, 8)])
        result = self.result()
        self.assertEqual(result["observed_total_tokens"], 36)
        self.assertEqual(result["coverage"]["unknown_token_events"], 1)

    def test_only_linked_parent_turn_is_coordinator_and_review_is_readonly(self):
        child = self.context("child")
        child["payload"]["root_turn_id"] = "linked"
        self.write([self.meta("child", agent_role="tvlk_ai_route_coding", source={"subagent": {"thread_spawn": {"parent_thread_id": "root"}}}, subagent_history_start_ordinal=1), child, self.token(1)], "child")
        self.write([self.meta(), self.context("linked"), self.token(2), self.context("manual"), self.token(3, 1)])
        before = {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        result = self.result()
        roles = {row["turn_id"]: row["category"] for row in result["details"]}
        self.assertEqual(roles["linked"], "coordinator")
        self.assertEqual(roles["manual"], "unknown")
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
