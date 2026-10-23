import unittest
from pathlib import Path

from csv_lens.compare import compare_csv
from csv_lens.io import CsvLensError, load_csv

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class TestCompare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = load_csv(str(FIXTURES / "customers_v1.csv"))
        cls.new = load_csv(str(FIXTURES / "customers_v2.csv"))
        cls.diff = compare_csv(cls.old, cls.new, key="customer_id")

    def test_schema_drift(self):
        self.assertEqual(self.diff.schema.added_columns, ["country"])
        self.assertEqual(self.diff.schema.removed_columns, ["signup_date"])
        self.assertFalse(self.diff.schema.reordered)

    def test_added_removed_rows(self):
        added = [r[0] for r in self.diff.added_rows]
        removed = [r[0] for r in self.diff.removed_rows]
        self.assertEqual(added, ["C007"])
        self.assertEqual(removed, ["C002"])

    def test_changed_cells(self):
        changes = {(c.key, c.column): (c.old_value, c.new_value)
                   for c in self.diff.changed_cells}
        self.assertEqual(changes[("C003", "city")], ("Lyon", "Marseille"))
        self.assertEqual(changes[("C005", "active")], ("yes", "no"))
        self.assertEqual(len(self.diff.changed_cells), 2)

    def test_duplicate_key_row_not_double_counted(self):
        # C006 appears twice (identical) in v1 and once in v2:
        # no change should be reported for it.
        keys = [c.key for c in self.diff.changed_cells]
        self.assertNotIn("C006", keys)

    def test_duplicate_keys_detected(self):
        dup = load_csv(str(FIXTURES / "duplicate_keys.csv"))
        other = load_csv(str(FIXTURES / "duplicate_keys.csv"))
        d = compare_csv(dup, other, key="order_id")
        self.assertEqual(d.duplicate_keys_old, ["O2"])
        self.assertTrue(any("Duplicate key" in w for w in d.warnings))

    def test_missing_key_column_raises(self):
        with self.assertRaises(CsvLensError) as ctx:
            compare_csv(self.old, self.new, key="no_such_col")
        self.assertIn("not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
