# CSV Lens

A local-first, zero-dependency (Python stdlib only) command-line tool that profiles CSV files for data-quality issues and diffs two CSV versions — for analysts and engineers who need to trust a dataset before using it, without uploading anything anywhere.

## Quickstart

Requires Python 3.10+ (tested on 3.10–3.13 in CI). No dependencies, no install step — run from the repository root so the module is importable from the working directory:

```bash
python -m csv_lens profile fixtures/customers_v1.csv --html report.html --json summary.json
```

Open `report.html` in any browser. Done. No install step, no network, no dependencies.

## Demo walkthrough (fixtures included)

```bash
# 1. Profile a CSV: types, missingness, duplicates, mixed types, outliers, categories
python -m csv_lens profile fixtures/customers_v1.csv --html demo_profile.html --json demo_profile.json

# 2. Diff two versions of the same dataset on a key column
python -m csv_lens diff fixtures/customers_v1.csv fixtures/customers_v2.csv \
    --key customer_id --html demo_diff.html --json demo_diff.json

# 3. A file that is not valid UTF-8 (auto-detected, warned about, still profiled)
python -m csv_lens profile fixtures/malformed_encoding.csv --html demo_malformed.html

# 4. A file with obvious numeric outliers (1.5*IQR rule)
python -m csv_lens profile fixtures/outliers.csv --html demo_outliers.html
```

The diff prints a console summary like:

```
Schema: +1 columns ['country'] -1 columns ['signup_date'] reordered=False
Rows (key 'customer_id'): 1 added, 1 removed, 2 cells changed
  duplicate keys: old=['C006'] new=[]
  C003 | city: 'Lyon' -> 'Marseille'
  C005 | active: 'yes' -> 'no'
  warning: Duplicate key values detected; for duplicated keys the LAST row in each file is used for change detection.
```

## Features

- **Profiling**: per-column inferred type (int / float / date / string), missing values (`""`, `NA`, `null`, …), distinct counts, category distributions for low-cardinality columns.
- **Findings**: exact duplicate full rows, suspicious mixed-type columns, high-cardinality (likely-ID) columns, and numeric outlier candidates via the transparent `1.5*IQR` fence rule (min 4 values, zero-IQR columns skipped).
- **Diffing**: schema diff (added / removed / reordered columns), key-based added / removed rows, and cell-level changes (`key | column: old -> new`). Duplicate keys are flagged; the last row wins for change detection and this is always warned about.
- **Robust loading**: delimiter auto-sniffing (`,` `;` tab `|`), encoding auto-detection (UTF-8 → cp1252 → latin-1) with explicit `--encoding` / `--delimiter` overrides, ragged-row padding with warnings, undecodable bytes replaced with U+FFFD and counted.
- **Reports**: self-contained interactive HTML (sortable columns, live row filter, zero external assets) plus a machine-readable JSON summary (`--json`).
- **Safety**: files are opened read-only. No value is ever coerced and no row is ever deleted — findings are reported, data is untouched. No telemetry, no network access.

> **Note on outliers:** statistical outliers are *review candidates*, not necessarily errors. A salary of 250000 in a list of ~60000s deserves a look — it may be perfectly correct.

## Usage

```
python -m csv_lens profile FILE.csv [--delimiter D] [--encoding E] [--html OUT.html] [--json OUT.json]
python -m csv_lens diff OLD.csv NEW.csv --key COLUMN [--delimiter D] [--encoding E] [--html OUT.html] [--json OUT.json]
```

## Fixtures

| File | Purpose |
|---|---|
| `customers_v1.csv` / `customers_v2.csv` | schema drift + added/removed rows + changed cells + a duplicate row |
| `outliers.csv` | numeric outliers (1.5*IQR) |
| `duplicate_keys.csv` | duplicate key values for diffing |
| `malformed_encoding.csv` | cp1252 bytes, invalid as UTF-8 |
| `empty.csv` / `blank.csv` | empty / whitespace-only files (graceful errors) |

## Tests

```bash
python -m pytest -q        # or: python -m unittest discover -v
```

42 tests covering loading edge cases, profiling rules, diffing, HTML/JSON report generation (including HTML-escaping of data values), and the CLI end to end. Fully deterministic, no network.

## Known limitations

- Files are loaded fully into memory; multi-GB files are out of scope for v1.
- Outlier detection uses only the 1.5*IQR rule on numeric columns (no z-score, no per-group rules).
- Diff compares rows by a single key column; duplicate keys resolve to the last row (with a warning).
- Type inference recognizes ISO dates only (`YYYY-MM-DD[ HH:MM[:SS]]`).
- HTML preview table shows at most 500 rows (findings always cover the full file).

## Roadmap

1. Streaming mode for large files (chunked profiling with reservoir sampling).
2. Configurable rules file (thresholds, per-column overrides, custom missing tokens).
3. Multi-key / composite-key diffing and row-moved detection.

## License

MIT — see [LICENSE](LICENSE).
