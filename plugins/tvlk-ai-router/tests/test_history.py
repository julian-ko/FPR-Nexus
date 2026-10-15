import json
import sqlite3
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

    def test_complete_views_reconcile_and_missing_turns_remain_visible(self):
        self.write([self.meta(), self.context(model="gpt-6-luna"), self.token(10)], "main")
        self.write([self.meta("no-events"), self.context(model="gpt-6-astra")], "empty")
        child = self.context("child", "gpt-6.1-sol")
        child["payload"]["root_turn_id"] = "t"
        self.write([self.meta("child", agent_role="tvlk_ai_route_coding", source={"subagent": {"thread_spawn": {"parent_thread_id": "root"}}}, subagent_history_start_ordinal=1), child, self.token(3)], "child")
        result = self.run_report()
        compare = result["scope_comparison"]
        self.assertEqual(compare["all"]["execution_turns"], 3)
        self.assertEqual(compare["nexus"]["execution_turns"], 2)
        self.assertEqual(compare["unattributed"]["execution_turns"], 1)
        self.assertEqual(result["turns_without_observed_events"], 1)
        self.assertEqual(result["unknown_attribution_turns"], 1)
        for name in ("model", "task", "date", "activity"):
            self.assertEqual(sum(Decimal(g["estimated_credits"]) for g in result["by_" + name]), Decimal(result["estimated_credits"]))
        row = next(g for g in result["by_model"] if g["group"] == "gpt-6-astra")
        self.assertEqual(row["turns_without_observed_events"], 1)
        self.assertEqual(row["estimate_status"], "partial")
        linked = next(r for r in result["routing_records"] if r["thread_id"] == "child")
        self.assertEqual((linked["parent_thread_id"], linked["parent_turn_id"]), ("root", "t"))

    def test_cache_cost_split_and_reasoning_subset(self):
        event = self.token(100)
        for name in ("total_token_usage", "last_token_usage"):
            event["payload"]["info"][name].update(cached_input_tokens=80, reasoning_output_tokens=60)
        self.write([self.meta(), self.context(model="gpt-6-luna"), event])
        result = self.run_report()
        self.assertEqual(result["observed_tokens"]["uncached_input_tokens"], 20)
        self.assertEqual(result["observed_tokens"]["total_tokens"], 200)
        self.assertEqual(Decimal(result["credit_breakdown"]["uncached_input"]), Decimal("0.00005"))
        self.assertEqual(sum(Decimal(x) for x in result["credit_breakdown"].values()), Decimal(result["estimated_credits"]))

    def test_missing_cache_and_missing_usage_not_free_or_zero_filled(self):
        event = self.token(10)
        for name in ("total_token_usage", "last_token_usage"):
            event["payload"]["info"][name].pop("cached_input_tokens")
        self.write([self.meta(), self.context(model="gpt-6-luna"), event,
                    self.record("event_msg", {"type": "token_count", "info": None})])
        result = self.run_report()
        self.assertEqual(result["unpriced_events"], 2)
        self.assertEqual(result["missing_fields"]["uncached_input_tokens"], 2)
        self.assertEqual(result["estimate_status"], "partial")
        self.assertEqual(result["credit_breakdown_missing_events"], 2)

    def test_model_and_date_turn_counts_not_additive(self):
        event = self.token(15, 5)
        event["timestamp"] = "2026-10-12T00:00:00Z"
        self.write([self.meta(), self.context(model="gpt-6-luna"), self.token(10), event])
        from datetime import timedelta
        result = report(self.manager(), now=self.now + timedelta(hours=1))
        self.assertEqual(result["execution_turns"], 1)
        self.assertEqual(len(result["by_date"]), 2)
        self.assertEqual(sum(g["execution_turns"] for g in result["by_date"]), 2)

    def test_old_ledger_prices_and_missing_source_survive_upgrade(self):
        self.write([self.meta(), self.context(model="gpt-6-luna"), self.token(10)])
        first = self.run_report()
        db = sqlite3.connect(first["history_file"])
        body = json.loads(db.execute("SELECT body FROM events").fetchone()[0])
        body.pop("unit_rates")
        db.execute("UPDATE events SET body=?", (json.dumps(body),))
        db.execute("UPDATE files SET stamp='old-parser'")
        db.commit()
        db.close()
        with patch("tvlk_ai_router.history.RATES", {"gpt-6-luna": (999, 999, 999)}):
            upgraded = self.run_report()
        self.assertEqual(upgraded["estimated_credits"], first["estimated_credits"])
        self.assertEqual(upgraded["credit_breakdown"], first["credit_breakdown"])
        (self.home / "sessions/a.jsonl").unlink()
        self.assertEqual(self.run_report()["estimated_credits"], first["estimated_credits"])

    def test_text_report_contains_full_sections_and_partial_labels(self):
        from tvlk_ai_router.review_text import render
        self.write([self.meta(), self.context(model="gpt-6-luna"), self.token(10)])
        output = render(self.run_report())
        for text in ("Nexus is a subset", "Uncached input", "Cached input", "Reasoning (already in output)",
                     "Task types", "Daily usage (UTC)", "Execution roles", "Unknown task turns", "Rates (credits per 1 million tokens)", "not an invoice"):
            self.assertIn(text, output)
