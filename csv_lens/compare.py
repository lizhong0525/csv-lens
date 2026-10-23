"""Compare two CSV versions: schema diff and key-column row/cell diff."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .io import CsvLensError, LoadedCsv


@dataclass
class SchemaDiff:
    added_columns: list[str]
    removed_columns: list[str]
    reordered: bool
    common_columns: list[str]


@dataclass
class CellChange:
    key: str
    column: str
    old_value: str
    new_value: str


@dataclass
class DiffResult:
    schema: SchemaDiff
    key_column: str
    added_rows: list[list[str]]
    removed_rows: list[list[str]]
    changed_cells: list[CellChange]
    duplicate_keys_old: list[str]
    duplicate_keys_new: list[str]
    warnings: list[str] = field(default_factory=list)


def compare_csv(old: LoadedCsv, new: LoadedCsv, key: str) -> DiffResult:
    if key not in old.headers:
        raise CsvLensError(
            f"Key column '{key}' not found in old file. "
            f"Available: {', '.join(old.headers)}")
    if key not in new.headers:
        raise CsvLensError(
            f"Key column '{key}' not found in new file. "
            f"Available: {', '.join(new.headers)}")

    schema = SchemaDiff(
        added_columns=[h for h in new.headers if h not in old.headers],
        removed_columns=[h for h in old.headers if h not in new.headers],
        reordered=([h for h in old.headers if h in new.headers]
                   != [h for h in new.headers if h in old.headers]),
        common_columns=[h for h in old.headers if h in new.headers],
    )

    def key_index(data: LoadedCsv) -> dict[str, list[str]]:
        idx = data.headers.index(key)
        return {row[idx]: row for row in data.rows}

    def dup_keys(data: LoadedCsv) -> list[str]:
        idx = data.headers.index(key)
        counts = Counter(row[idx] for row in data.rows)
        return sorted(k for k, c in counts.items() if c > 1)

    old_keys = key_index(old)
    new_keys = key_index(new)
    dups_old, dups_new = dup_keys(old), dup_keys(new)

    warnings: list[str] = []
    if dups_old or dups_new:
        warnings.append(
            "Duplicate key values detected; for duplicated keys the LAST "
            "row in each file is used for change detection.")

    added_keys = sorted(k for k in new_keys if k not in old_keys)
    removed_keys = sorted(k for k in old_keys if k not in new_keys)

    changes: list[CellChange] = []
    for k in sorted(old_keys.keys() & new_keys.keys()):
        old_row, new_row = old_keys[k], new_keys[k]
        for col in schema.common_columns:
            if col == key:
                continue
            ov = old_row[old.headers.index(col)]
            nv = new_row[new.headers.index(col)]
            if ov != nv:
                changes.append(CellChange(key=k, column=col,
                                          old_value=ov, new_value=nv))

    return DiffResult(
        schema=schema, key_column=key,
        added_rows=[new_keys[k] for k in added_keys],
        removed_rows=[old_keys[k] for k in removed_keys],
        changed_cells=changes,
        duplicate_keys_old=dups_old, duplicate_keys_new=dups_new,
        warnings=warnings,
    )
