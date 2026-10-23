import json
import os
import tempfile
import unittest
from pathlib import Path

from csv_lens.compare import compare_csv
from csv_lens.io import load_csv
from csv_lens.profile import profile_csv
from csv_lens.report import (diff_to_dict, profile_to_dict,
                             render_diff_report, render_profile_report,
                             write_json)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class TestReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv(str(FIXTURES / "customers_v1.csv"))
        cls.profile = profile_csv(cls.data)

    def test_html_report_is_self_contained(self):
        html_doc = render_profile_report(self.profile, self.data)
        self.assertTrue(html_doc.startswith("<!DOCTYPE html>"))
        self.assertIn("<style>", html_doc)  # inline CSS, no external assets
        self.assertNotIn("http://", html_doc.replace("http://www.w3.org", ""))
        self.assertNotIn("https://", html_doc)
        # interactive bits
        self.assertIn("sortTable", html_doc)
        self.assertIn("filterTable", html_doc)
        # content
        self.assertIn("mixed types", html_doc)
        self.assertIn("duplicate", html_doc)
        self.assertIn("Berlin", html_doc)  # preview data present
        # the mandatory disclaimer
        self.assertIn("review candidates", html_doc)

    def test_html_escapes_values(self):
        import csv as csvmod
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "xss.csv")
            with open(p, "w", newline="", encoding="utf-8") as fh:
                w = csvmod.writer(fh)
                w.writerow(["id", "note"])
                w.writerow(["1", "<script>alert(1)</script>"])
            data = load_csv(p)
            html_doc = render_profile_report(profile_csv(data), data)
            self.assertNotIn("<script>alert(1)</script>", html_doc)
            self.assertIn("&lt;script&gt;", html_doc)

    def test_json_summary_roundtrip(self):
        summary = profile_to_dict(self.profile, self.data)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "summary.json")
            write_json(summary, p)
            loaded = json.loads(open(p, encoding="utf-8").read())
        self.assertEqual(loaded["rows"], 7)
        self.assertEqual(loaded["duplicate_rows"], 1)
        self.assertIn("rules", loaded)
        self.assertEqual(len(loaded["column_profiles"]), 6)
        age = next(c for c in loaded["column_profiles"] if c["name"] == "age")
        self.assertTrue(age["mixed_type_suspicious"])
        self.assertEqual(age["missing_count"], 1)

    def test_diff_report(self):
        old = self.data
        new = load_csv(str(FIXTURES / "customers_v2.csv"))
        diff = compare_csv(old, new, key="customer_id")
        html_doc = render_diff_report(diff, old, new)
        self.assertIn("C007", html_doc)  # added row
        self.assertIn("C002", html_doc)  # removed row
        self.assertIn("Marseille", html_doc)  # changed cell new value
        self.assertIn("country", html_doc)  # added column
        d = diff_to_dict(diff)
        self.assertEqual([r[0] for r in d["added_rows"]], ["C007"])
        self.assertEqual(len(d["changed_cells"]), 2)


if __name__ == "__main__":
    unittest.main()
