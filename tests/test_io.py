import unittest
from pathlib import Path

from csv_lens.io import CsvLensError, load_csv, sniff_delimiter

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class TestLoading(unittest.TestCase):
    def test_basic_load(self):
        data = load_csv(str(FIXTURES / "customers_v1.csv"))
        self.assertEqual(data.headers[0], "customer_id")
        self.assertEqual(data.n_rows, 7)
        self.assertEqual(data.delimiter, ",")
        self.assertEqual(data.encoding, "utf-8-sig")

    def test_delimiter_sniffing(self):
        self.assertEqual(sniff_delimiter("a;b;c\n1;2;3\n"), ";")
        self.assertEqual(sniff_delimiter("a\tb\n1\t2\n"), "\t")
        self.assertEqual(sniff_delimiter("a,b\n1,2\n"), ",")

    def test_explicit_delimiter(self):
        data = load_csv(str(FIXTURES / "customers_v1.csv"), delimiter=",")
        self.assertEqual(data.delimiter, ",")

    def test_malformed_encoding_falls_back(self):
        data = load_csv(str(FIXTURES / "malformed_encoding.csv"))
        self.assertTrue(data.encoding_fallback)
        self.assertNotEqual(data.encoding, "utf-8")
        self.assertEqual(data.n_rows, 2)
        # cp1252 fallback decodes the bytes readably
        self.assertIn("rôme", data.rows[0][1])

    def test_explicit_wrong_encoding_counts_replacements(self):
        data = load_csv(str(FIXTURES / "malformed_encoding.csv"),
                        encoding="utf-8")
        self.assertGreater(data.replaced_chars, 0)
        self.assertTrue(any("replaced" in w for w in data.warnings))

    def test_empty_file_raises(self):
        with self.assertRaises(CsvLensError) as ctx:
            load_csv(str(FIXTURES / "empty.csv"))
        self.assertIn("empty", str(ctx.exception).lower())

    def test_blank_file_raises(self):
        with self.assertRaises(CsvLensError):
            load_csv(str(FIXTURES / "blank.csv"))

    def test_missing_file_raises(self):
        with self.assertRaises(CsvLensError) as ctx:
            load_csv(str(FIXTURES / "does_not_exist.csv"))
        self.assertIn("not found", str(ctx.exception).lower())

    def test_ragged_rows_padded_with_warning(self, tmp_path=None):
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ragged.csv")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("a,b,c\n1,2,3\n4,5\n6,7,8,9\n")
            data = load_csv(p)
            self.assertEqual(data.row_length_mismatches, 2)
            self.assertEqual(data.rows[1], ["4", "5", ""])
            self.assertEqual(data.rows[2], ["6", "7", "8"])
            self.assertTrue(any("column count" in w for w in data.warnings))


if __name__ == "__main__":
    unittest.main()
