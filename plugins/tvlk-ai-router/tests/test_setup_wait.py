import contextlib
import io
import subprocess
import unittest
from unittest.mock import patch

from test_migration import setup_helper, PACKAGE


class SetupWaitTests(unittest.TestCase):
    def test_waits_until_all_clients_exit_and_stay_closed(self):
        checks = [["1:chatgpt"], ["1:chatgpt"], [], ["2:codex"], [], []]
        with patch.object(setup_helper, "running_clients", side_effect=checks) as scan, \
                patch.object(setup_helper.time, "sleep") as sleep, \
                patch.object(setup_helper.subprocess, "run") as install, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            def run(*args, **kwargs):
                self.assertEqual(scan.call_count, 6)
                return subprocess.CompletedProcess(args, 0)
            install.side_effect = run
            self.assertEqual(setup_helper.run_install(PACKAGE), 0)
            self.assertEqual(sleep.call_count, 5)
            install.assert_called_once()
            self.assertEqual(output.getvalue().count("Waiting for clients to exit:"), 2)

    def test_no_clients_continues_without_input(self):
        with patch.object(setup_helper, "running_clients", return_value=[]), \
                patch.object(setup_helper.time, "sleep"), \
                patch("builtins.input", side_effect=AssertionError("must not prompt")), \
                patch.object(setup_helper.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as install:
            self.assertEqual(setup_helper.run_install(PACKAGE), 0)
            self.assertIn("scripts/install.py", install.call_args.args[0][-1])

    def test_scan_failure_does_not_start_install(self):
        with patch.object(setup_helper, "running_clients", side_effect=RuntimeError("ps failed")), \
                patch.object(setup_helper.subprocess, "run") as install:
            with self.assertRaisesRegex(RuntimeError, "ps failed"):
                setup_helper.run_install(PACKAGE)
            install.assert_not_called()

    def test_cancel_while_waiting_does_not_start_install(self):
        with patch.object(setup_helper, "running_clients", return_value=["1:codex"]), \
                patch.object(setup_helper.time, "sleep", side_effect=KeyboardInterrupt), \
                patch.object(setup_helper.subprocess, "run") as install, \
                patch("sys.argv", ["setup.py", "--install"]):
            self.assertEqual(setup_helper.main(), 130)
            install.assert_not_called()

    def test_installer_write_guard_failure_is_not_reported_as_success(self):
        with patch.object(setup_helper, "running_clients", return_value=[]), \
                patch.object(setup_helper.time, "sleep"), \
                patch.object(setup_helper.subprocess, "run", return_value=subprocess.CompletedProcess([], 4)):
            self.assertEqual(setup_helper.run_install(PACKAGE), 4)


if __name__ == "__main__":
    unittest.main()
