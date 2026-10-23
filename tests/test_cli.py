import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "csv_lens", *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60)


class TestCli(unittest.TestCase):
    def test_profile_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            html_path = os.path.join(td, "report.html")
            json_path = os.path.join(td, "summary.json")
            r = run_cli("profile", str(FIXTURES / "customers_v1.csv"),
                        "--html", html_path, "--json", json_path)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("7 rows x 6 columns", r.stdout)
            self.assertIn("mixed types", r.stdout)
            self.assertTrue(os.path.isfile(html_path))
            self.assertTrue(os.path.isfile(json_path))
            summary = json.load(open(json_path, encoding="utf-8"))
            self.assertEqual(summary["rows"], 7)

    def test_diff_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            html_path = os.path.join(td, "diff.html")
            r = run_cli("diff",
                        str(FIXTURES / "customers_v1.csv"),
                        str(FIXTURES / "customers_v2.csv"),
                        "--key", "customer_id", "--html", html_path)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("1 added", r.stdout)
            self.assertIn("1 removed", r.stdout)
            self.assertIn("2 cells changed", r.stdout)
            self.assertTrue(os.path.isfile(html_path))

    def test_empty_file_exit_code_and_message(self):
        r = run_cli("profile", str(FIXTURES / "empty.csv"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("empty", r.stderr.lower())

    def test_missing_file_exit_code(self):
        r = run_cli("profile", str(FIXTURES / "nope.csv"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found", r.stderr.lower())

    def test_malformed_encoding_still_profiles(self):
        with tempfile.TemporaryDirectory() as td:
            html_path = os.path.join(td, "r.html")
            r = run_cli("profile",
                        str(FIXTURES / "malformed_encoding.csv"),
                        "--html", html_path)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("warning", r.stdout.lower())

    def test_diff_requires_key(self):
        r = run_cli("diff", str(FIXTURES / "customers_v1.csv"),
                    str(FIXTURES / "customers_v2.csv"))
        self.assertNotEqual(r.returncode, 0)

    def test_diff_bad_key_message(self):
        r = run_cli("diff", str(FIXTURES / "customers_v1.csv"),
                    str(FIXTURES / "customers_v2.csv"), "--key", "zzz")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found", r.stderr)


if __name__ == "__main__":
    unittest.main()
