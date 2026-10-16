import json
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_usage as fixtures
from tvlk_ai_router.config import RouterError
from tvlk_ai_router.history import report
from tvlk_ai_router.review_text import render
from tvlk_ai_router.usage_export import dataset, save


class ExportTests(unittest.TestCase):
    setUp, tearDown = fixtures.UsageTests.setUp, fixtures.UsageTests.tearDown
    record, meta, context, token, write = (fixtures.UsageTests.record, fixtures.UsageTests.meta,
        fixtures.UsageTests.context, fixtures.UsageTests.token, fixtures.UsageTests.write)

    def snapshot(self, **kwargs):
        manager = SimpleNamespace(home=self.home, data=self.home / "state", state={"installed_at": "2026-10-10T00:00:00Z"})
        return dataset(report(manager, now=self.now, **kwargs))

    def test_effort_groups_records_scope_and_missing_data_reconcile(self):
        high = self.context("high", "gpt-6-luna")
        high["payload"]["effort"] = "high"
        self.write([self.meta(), self.context(model="gpt-6-luna"), self.token(10),
                    self.record("response_item", {"secret_prompt": "SECRET_NOT_FOR_EXPORT"})])
        self.write([self.meta("high"), high, self.token(20)], "high")
        self.write([self.meta("empty"), self.context("empty", "unknown-model")], "empty")
        result = self.snapshot()
        groups = result["by_model_reasoning_effort"]
        self.assertEqual({r["reasoning_effort"] for r in groups if r["model"] == "gpt-6-luna"}, {"medium", "high"})
        self.assertEqual(result["summary"]["turns_without_observed_events"], 1)
        self.assertEqual(result["summary"]["execution_turns"], 3)
        for rows in (groups, result["by_date_model_reasoning_task"]):
            self.assertEqual(sum(Decimal(r["estimated_credits"]) for r in rows), Decimal(result["summary"]["estimated_credits"]))
            self.assertEqual(sum(r["observed_tokens"]["total_tokens"] for r in rows), result["summary"]["observed_tokens"]["total_tokens"])
        records = result["records"]
        self.assertEqual(len(records), result["summary"]["usage_events"])
        self.assertEqual(len({r["event_id"] for r in records}), len(records))
        self.assertEqual({r["task_type"] for r in records}, {"unknown"})
        self.assertTrue(all(isinstance(r["estimated_credits"], str) for r in records))
        self.assertNotIn("SECRET_NOT_FOR_EXPORT", json.dumps(result))
        self.assertNotIn(str(self.home), json.dumps(result))
        self.assertFalse(result["measurement"]["analysis_included"])
        self.assertEqual(self.snapshot(scope="nexus")["records"], [])
        self.assertEqual(self.snapshot(since="2026-10-12")["records"], [])

    def test_pair_is_private_matches_snapshot_and_does_not_overwrite(self):
        self.write([self.meta(), self.context(model="gpt-6-luna"), self.token(10)])
        result = self.snapshot()
        directory = self.home / "exports"
        first = save(result, directory)
        original = Path(first["json"]).read_bytes()
        self.assertEqual(json.loads(original), result)
        self.assertEqual(Path(first["table"]).read_text(), render(result) + "\n")
        second = save(self.snapshot(), directory)
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first["json"]).read_bytes(), original)
        self.assertEqual(json.loads(Path(second["json"]).read_text())["records"], result["records"])
        for path in map(Path, first.values()):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        (self.home / "sessions/a.jsonl").unlink()
        self.assertEqual(self.snapshot()["records"], result["records"])

    def test_second_file_failure_leaves_no_half_pair_and_keeps_prior_export(self):
        directory = self.home / "exports"
        prior = save(self.snapshot(), directory)
        content = Path(prior["json"]).read_bytes()
        import os
        sync = os.fsync
        calls = []
        def fail_second(fd):
            calls.append(fd)
            if len(calls) == 2:
                raise OSError("disk full")
            sync(fd)
        with patch("tvlk_ai_router.usage_export.os.fsync", side_effect=fail_second), self.assertRaises(OSError):
            save(self.snapshot(), directory)
        self.assertEqual(list(directory.iterdir()), [Path(prior["json"]).parent])
        self.assertEqual(Path(prior["json"]).read_bytes(), content)

    def test_symlink_export_path_is_rejected(self):
        outside = self.home / "outside"
        outside.mkdir()
        directory = self.home / "exports"
        directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(RouterError):
            save(self.snapshot(), directory)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unknown_prices_and_token_fields_remain_unknown(self):
        token = self.token(10)
        for key in ("total_token_usage", "last_token_usage"):
            token["payload"]["info"][key].pop("cached_input_tokens")
        self.write([self.meta(), self.context(model="unknown-model"), token])
        result = self.snapshot()
        self.assertIsNone(result["records"][0]["estimated_credits"])
        self.assertIsNone(result["records"][0]["token_usage"]["uncached_input_tokens"])
        self.assertIsNone(result["records"][0]["credit_breakdown"])
        self.assertEqual(result["summary"]["unpriced_events"], 1)
        self.assertEqual(result["summary"]["estimate_status"], "partial")
        self.assertNotIn("Largest observed", render(result))
