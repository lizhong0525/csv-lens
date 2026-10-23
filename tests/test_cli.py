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

    def test_unknown_encoding_clean_error(self):
        r = run_cli("profile", str(FIXTURES / "customers_v1.csv"),
                    "--encoding", "bogus-enc")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Unknown encoding", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_multi_char_delimiter_clean_error(self):
        r = run_cli("profile", str(FIXTURES / "customers_v1.csv"),
                    "--delimiter", ";;")
        self.assertEqual(r.returncode, 2)
        self.assertIn("single character", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_directory_instead_of_file(self):
        r = run_cli("profile", str(FIXTURES))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Not a regular file", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_oversized_field_clean_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "big.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("a,b\n" + "x" * 200000 + ",y\n")
            r = run_cli("profile", path)
            self.assertEqual(r.returncode, 2)
            self.assertIn("Could not parse", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_console_output_survives_unencodable_chars(self):
        # Simulate a legacy-codepage console (e.g. Windows GBK) where data
        # contains characters the output encoding cannot represent.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "emoji.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("id,备注🌍\n1,x\n2,y\n")
            env = dict(os.environ, PYTHONIOENCODING="gbk:strict")
            r = subprocess.run(
                [sys.executable, "-m", "csv_lens", "profile", path,
                 "--html", os.path.join(td, "r.html")],
                cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", env=env, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
