"""Column profiling: type inference, missingness, outliers, cardinality.

All statistics are computed from the raw strings as loaded. Nothing is
written back and no value is coerced in the source data. Outliers use the
transparent 1.5*IQR fence rule and are review candidates, NOT errors.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from .io import LoadedCsv

MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "-"}
INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")

# Thresholds are part of the transparent rule set and shown in the report.
MIXED_TYPE_MINORITY = 0.05     # minority type share >= 5% ...
MIXED_TYPE_DOMINANT = 0.95     # ... while dominant share < 95% => suspicious
HIGH_CARDINALITY_RATIO = 0.9   # distinct/rows >= 90% => likely unique key
HIGH_CARDINALITY_MIN_ROWS = 20
OUTLIER_IQR_FACTOR = 1.5
MAX_OUTLIERS_LISTED = 50
MAX_TOP_CATEGORIES = 10
LOW_CARDINALITY_LIMIT = 25     # show full distribution at or below this


def _classify(value: str) -> str:
    """Classify a single non-missing value as int/float/date/string."""
    if INT_RE.match(value):
        return "int"
    if FLOAT_RE.match(value):
        return "float"
    if DATE_RE.match(value):
        return "date"
    return "string"


def is_missing(value: str) -> bool:
    return value.strip().lower() in MISSING_TOKENS


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str
    type_counts: dict[str, int]
    mixed_type_suspicious: bool
    missing_count: int
    missing_pct: float
    distinct_count: int
    cardinality_ratio: float
    high_cardinality: bool
    numeric: dict[str, float] | None = None
    outlier_count: int = 0
    outliers: list[tuple[int, str]] = field(default_factory=list)
    top_categories: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class Profile:
    headers: list[str]
    n_rows: int
    columns: list[ColumnProfile]
    duplicate_row_count: int
    duplicate_row_examples: list[list[str]]
    warnings: list[str]


def _numeric_summary(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def _iqr_outliers(indexed: list[tuple[int, float]]) -> tuple[int, list[tuple[int, str]]]:
    """1.5*IQR fences. Returns (total_outlier_count, capped listed examples)."""
    if len(indexed) < 4:
        return 0, []
    vals = sorted(v for _, v in indexed)
    q1, q3 = statistics.quantiles(vals, n=4, method="inclusive")[0], \
        statistics.quantiles(vals, n=4, method="inclusive")[2]
    iqr = q3 - q1
    if iqr == 0:
        return 0, []
    lo = q1 - OUTLIER_IQR_FACTOR * iqr
    hi = q3 + OUTLIER_IQR_FACTOR * iqr
    hits = [(row, v) for row, v in indexed if v < lo or v > hi]
    listed = [(row, repr(v)) for row, v in hits[:MAX_OUTLIERS_LISTED]]
    return len(hits), listed


def profile_column(name: str, values: list[str], n_rows: int) -> ColumnProfile:
    present = [(i, v) for i, v in enumerate(values) if not is_missing(v)]
    missing = n_rows - len(present)
    type_counts = Counter(_classify(v.strip()) for _, v in present)
    total_present = max(len(present), 1)
    dominant, dominant_n = ("string", 0)
    if type_counts:
        dominant, dominant_n = max(type_counts.items(), key=lambda kv: kv[1])
    shares = {t: c / total_present for t, c in type_counts.items()}
    suspicious = (
        len(type_counts) > 1
        and dominant_n / total_present < MIXED_TYPE_DOMINANT
        and any(s >= MIXED_TYPE_MINORITY for t, s in shares.items() if t != dominant)
    )
    inferred = dominant
    if dominant in ("int", "float") and (type_counts.get("int", 0) + type_counts.get("float", 0)) / total_present >= MIXED_TYPE_DOMINANT:
        inferred = "float" if type_counts.get("float") else "int"

    distinct_values = {v.strip() for _, v in present}
    distinct = len(distinct_values)
    ratio = distinct / total_present
    high_card = (
        ratio >= HIGH_CARDINALITY_RATIO and n_rows >= HIGH_CARDINALITY_MIN_ROWS
    )

    numeric = None
    outlier_count = 0
    outliers: list[tuple[int, str]] = []
    numeric_vals: list[tuple[int, float]] = []
    for i, v in present:
        if _classify(v.strip()) in ("int", "float"):
            try:
                numeric_vals.append((i, float(v.strip())))
            except ValueError:
                pass
    if numeric_vals and len(numeric_vals) / total_present >= MIXED_TYPE_DOMINANT:
        numeric = _numeric_summary([v for _, v in numeric_vals])
        outlier_count, outliers = _iqr_outliers(numeric_vals)

    top_categories: list[tuple[str, int]] = []
    if not high_card and distinct <= LOW_CARDINALITY_LIMIT:
        top_categories = Counter(v.strip() for _, v in present).most_common(MAX_TOP_CATEGORIES)

    return ColumnProfile(
        name=name, inferred_type=inferred, type_counts=dict(type_counts),
        mixed_type_suspicious=suspicious, missing_count=missing,
        missing_pct=100.0 * missing / max(n_rows, 1),
        distinct_count=distinct, cardinality_ratio=ratio,
        high_cardinality=high_card, numeric=numeric,
        outlier_count=outlier_count, outliers=outliers,
        top_categories=top_categories,
    )


def profile_csv(data: LoadedCsv) -> Profile:
    n = data.n_rows
    columns = [
        profile_column(h, [row[j] for row in data.rows], n)
        for j, h in enumerate(data.headers)
    ]
    seen: Counter[tuple[str, ...]] = Counter(tuple(r) for r in data.rows)
    dup_rows = sum(c - 1 for c in seen.values() if c > 1)
    dup_examples = [list(t) for t, c in seen.most_common() if c > 1][:5]
    return Profile(
        headers=data.headers, n_rows=n, columns=columns,
        duplicate_row_count=dup_rows, duplicate_row_examples=dup_examples,
        warnings=list(data.warnings),
    )
