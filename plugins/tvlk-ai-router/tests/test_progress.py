import io
import os
import unittest
from unittest.mock import patch

from tvlk_ai_router import cli
from tvlk_ai_router.config import RouterError
from tvlk_ai_router.progress import finish_progress, progress


class TerminalProgressTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.output.isatty = lambda: True
        self.environment = patch.dict(os.environ, TVLK_ROUTER_PROGRESS="text")
        self.stderr = patch("sys.stderr", self.output)
        self.environment.start()
        self.stderr.start()

    def tearDown(self):
        finish_progress()
        self.stderr.stop()
        self.environment.stop()

    def test_updates_share_one_line_and_clear_old_text(self):
        progress("copy", "A long stage name", 1, 10)
        progress("verify", "Verify", 5, 10)
        self.assertNotIn("\n", self.output.getvalue())
        self.assertEqual(self.output.getvalue().count("\r\033[2K"), 2)
        self.assertIn("50%", self.output.getvalue())
        finish_progress()
        finish_progress()
        self.assertEqual(self.output.getvalue().count("\n"), 1)

    def test_long_line_cannot_wrap(self):
        progress("copy", "x" * 300, 2, 10)
        self.assertEqual(len(self.output.getvalue().split("\033[2K")[-1]), 79)

    def test_redirected_logs_use_plain_lines(self):
        self.output.isatty = lambda: False
        progress("copy", "Copy", 1, 10)
        progress("copy", "Copy", 2, 10)
        self.assertNotIn("\033", self.output.getvalue())
        self.assertEqual(self.output.getvalue().count("\n"), 2)

    def test_result_starts_after_bar(self):
        progress("copy", "Copy", 10, 10)
        with patch("sys.stdout", self.output):
            cli.display("Done")
        self.assertIn("\nDone\n", self.output.getvalue())

    def test_error_starts_after_bar(self):
        def fail(*args):
            progress("copy", "Copy", 1, 10)
            raise RouterError("Stopped safely", 4)
        with patch.object(cli, "Manager", side_effect=fail):
            self.assertEqual(cli.main(["apply"]), 4)
        self.assertIn("\nError: Stopped safely\n", self.output.getvalue())
