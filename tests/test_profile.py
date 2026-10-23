import unittest
from pathlib import Path

from csv_lens.io import load_csv
from csv_lens.profile import (is_missing, profile_column, profile_csv,
                              _classify)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class TestClassify(unittest.TestCase):
    def test_type_classification(self):
        self.assertEqual(_classify("42"), "int")
        self.assertEqual(_classify("-7"), "int")
        self.assertEqual(_classify("3.14"), "float")
        self.assertEqual(_classify("1e5"), "float")
        self.assertEqual(_classify("2023-01-15"), "date")
        self.assertEqual(_classify("2023-01-15 10:30"), "date")
        self.assertEqual(_classify("hello"), "string")

    def test_missing_tokens(self):
        for tok in ["", " ", "NA", "null", "None", "NaN", "-"]:
            self.assertTrue(is_missing(tok), tok)
        self.assertFalse(is_missing("0"))


class TestProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_csv(str(FIXTURES / "customers_v1.csv"))
        cls.profile = profile_csv(cls.data)
        cls.by_name = {c.name: c for c in cls.profile.columns}

    def test_shape(self):
        self.assertEqual(self.profile.n_rows, 7)
        self.assertEqual(len(self.profile.columns), 6)

    def test_duplicate_rows_detected_not_removed(self):
        self.assertEqual(self.profile.duplicate_row_count, 1)
        # rows are still all present in the loaded data
        self.assertEqual(self.data.n_rows, 7)

    def test_missingness(self):
        age = self.by_name["age"]
        self.assertEqual(age.missing_count, 1)

    def test_mixed_type_flagged(self):
        age = self.by_name["age"]  # ints + one "unknown"
        self.assertTrue(age.mixed_type_suspicious)
        self.assertIn("string", age.type_counts)

    def test_high_cardinality_id_column(self):
        cid = self.by_name["customer_id"]
        self.assertGreaterEqual(cid.cardinality_ratio, 0.8)

    def test_category_distribution_low_cardinality(self):
        active = self.by_name["active"]
        values = {v: n for v, n in active.top_categories}
        self.assertEqual(values.get("yes"), 4)
        self.assertEqual(values.get("no"), 3)

    def test_outliers_iqr(self):
        data = load_csv(str(FIXTURES / "outliers.csv"))
        prof = profile_csv(data)
        salary = next(c for c in prof.columns if c.name == "salary")
        self.assertEqual(salary.outlier_count, 2)  # 250000 and 5800
        vals = [float(v) for _, v in salary.outliers]
        self.assertIn(250000.0, vals)
        self.assertIn(5800.0, vals)

    def test_constant_column_has_no_outliers(self):
        prof = profile_column("x", ["5", "5", "5", "5", "5"], 5)
        self.assertEqual(prof.outlier_count, 0)

    def test_all_missing_column(self):
        prof = profile_column("x", ["", "NA", "null"], 3)
        self.assertEqual(prof.missing_count, 3)
        self.assertAlmostEqual(prof.missing_pct, 100.0)


if __name__ == "__main__":
    unittest.main()
