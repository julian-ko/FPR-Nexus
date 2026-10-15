import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from test_usage import UsageTests
from tvlk_ai_router.history import estimate, report
from tvlk_ai_router.config import RouterError


class HistoryTests(UsageTests):
    def manager(self):
        return SimpleNamespace(home=self.home, data=self.home / "state", state={"installed_at": "2026-10-10T00:00:00Z"})

    def run_report(self, **kwargs):
        return report(self.manager(), now=self.now, **kwargs)

    def test_price_cache_and_reasoning_are_not_added_twice(self):
        e = {"model": "gpt-6-luna", "speed": "unknown", "tokens": {
            "input_tokens": 1000000, "cached_input_tokens": 800000, "output_tokens": 100000,
            "reasoning_output_tokens": 90000}}
        self.assertEqual(Decimal(estimate(e)[0]), Decimal("1.95"))
        e["tokens"]["cached_input_tokens"] = None
        self.assertIsNone(estimate(e)[0])
        e["tokens"]["cached_input_tokens"] = 800000
        e["speed"] = "priority"
        self.assertIsNone(estimate(e)[0])

    def test_retention_dedup_and_incremental_import(self):
        self.write([self.meta(), self.context(model="gpt-6-luna"), self.token(10)])
        first = self.run_report()
        self.assertEqual(first["observed_tokens"]["total_tokens"], 20)
        with patch("tvlk_ai_router.history.review", side_effect=AssertionError("unchanged file must not be reparsed")):
            self.assertEqual(self.run_report()["estimated_credits"], first["estimated_credits"])
        self.write([self.meta(), self.context(model="gpt-6-luna"), self.token(10), self.token(15, 5)])
        self.assertEqual(self.run_report()["observed_tokens"]["total_tokens"], 30)
        (self.home / "sessions/a.jsonl").unlink()
        m = self.manager()
        m.state = None
        retained = report(m, "since-install", now=self.now)
        self.assertEqual(retained["observed_tokens"]["total_tokens"], 30)
        self.assertTrue((self.home / "fpr-nexus-history/usage.sqlite3").is_file())

    def test_cross_file_scope_and_dates(self):
        self.write([self.meta(), self.context(), self.token(2)], "parent")
        self.run_report()
        child = self.context("child", model="gpt-6.1-sol")
        child["payload"]["root_turn_id"] = "t"
        self.write([self.meta("child", agent_role="tvlk_ai_route_coding", source={"subagent": {"thread_spawn": {"parent_thread_id": "root"}}}, subagent_history_start_ordinal=1), child, self.token(3)], "child")
        self.write([self.meta("manual"), self.context(), self.token(5)], "manual")
        nexus = self.run_report(scope="nexus", group_by="task")
        self.assertEqual(nexus["observed_tokens"]["total_tokens"], 10)
        self.assertEqual({g["group"] for g in nexus["groups"]}, {"coordinator", "coding"})
        self.assertEqual(self.run_report()["observed_tokens"]["total_tokens"], 20)
        self.assertEqual(self.run_report(since="2026-10-11", until="2026-10-11", group_by="date")["groups"][0]["group"], "2026-10-11")
        with self.assertRaises(RouterError):
            self.run_report(since="bad")

    def test_unknown_usage_no_price_and_no_prompt_retention(self):
        self.write([self.meta(), self.context(model="unknown-model"), self.token(10),
                    self.record("response_item", {"secret_prompt": "DO NOT RETAIN THIS"})])
        result = self.run_report()
        self.assertEqual(result["unpriced_events"], 1)
        self.assertEqual(result["estimated_credits"], "0")
        self.assertNotIn(b"DO NOT RETAIN THIS", (self.home / "fpr-nexus-history/usage.sqlite3").read_bytes())
        (self.home / "fpr-nexus-history/usage.sqlite3").unlink()
        (self.home / "fpr-nexus-history/usage.sqlite3").symlink_to(self.home / "outside")
        with self.assertRaises(RouterError):
            self.run_report()

    def test_archived_copy_and_saved_price(self):
        rows = [self.meta(), self.context(model="gpt-6-luna"), self.token(10)]
        self.write(rows)
        first = self.run_report()
        self.write(rows, "copy")
        with patch("tvlk_ai_router.history.RATES", {"gpt-6-luna": (999, 999, 999)}):
            self.assertEqual(self.run_report()["estimated_credits"], first["estimated_credits"])
