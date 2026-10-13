import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]


class PythonDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name).resolve()
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin"}
        self.env.pop("TVLK_ROUTER_PYTHON", None)
        self.bad = self.bin / "python3"
        self.bad.write_text("#!/bin/bash\nexit 1\n")
        self.bad.chmod(0o700)

    def tearDown(self):
        self.temporary.cleanup()

    def resolve(self, explicit=""):
        return subprocess.run(["/bin/bash", "-c", 'source "$1"; tvlk_find_python "$2"',
                               "test", str(PACKAGE / "scripts/python.sh"), explicit],
                              capture_output=True, text=True, env=self.env)

    def good(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/bash\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
        path.chmod(0o700)
        return path

    def test_skips_old_default_and_finds_versioned_python(self):
        good = self.good(self.bin / "python3.12")
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(good))

    def test_reuses_existing_runtime_without_path_entry(self):
        good = self.good(self.home / ".local/share/tvlk-ai-router-plugin/runtime/.venv/bin/python")
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(good))

    def test_explicit_bad_python_does_not_silently_fallback(self):
        self.good(self.bin / "python3.12")
        result = self.resolve(str(self.bad))
        self.assertEqual(result.returncode, 4)
        self.assertIn("venv and ensurepip", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_environment_override_supports_spaces(self):
        good = self.good(self.home / "approved python/python3")
        self.env["TVLK_ROUTER_PYTHON"] = str(good)
        self.assertEqual(self.resolve().stdout.strip(), str(good))

    def test_chat_setup_accepts_explicit_python_and_only_prepares(self):
        good = self.good(self.home / "approved python/python3")
        result = subprocess.run(["/bin/bash", str(PACKAGE / "scripts/chat.sh"), "setup", "--python", str(good)],
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        command = Path(result.stdout.split("Setup file: ", 1)[1].strip())
        self.assertTrue(command.exists())
        self.assertFalse((self.home / ".local/share/tvlk-ai-router/state.json").exists())

    def test_both_entrypoints_reject_missing_argument(self):
        for script, args in (("install.sh", []), ("scripts/chat.sh", ["setup"])):
            result = subprocess.run(["/bin/bash", str(PACKAGE / script), *args, "--python"],
                                    capture_output=True, text=True, env=self.env)
            self.assertEqual(result.returncode, 2)
            self.assertIn("requires an interpreter path", result.stderr)
