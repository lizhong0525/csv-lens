"""CSV loading with delimiter sniffing and transparent encoding handling.

Loading is read-only: values are never coerced, rows are never dropped.
Undecodable bytes are replaced with U+FFFD and counted so the report can
surface exactly how much data was affected.
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field

CANDIDATE_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
SNIFF_SAMPLE_BYTES = 64 * 1024
MAX_COLUMNS = 1000


class CsvLensError(Exception):
    """User-facing error with a meaningful message."""


@dataclass
class LoadedCsv:
    path: str
    headers: list[str]
    rows: list[list[str]]
    delimiter: str
    encoding: str
    encoding_fallback: bool
    replaced_chars: int
    row_length_mismatches: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return len(self.rows)


def sniff_delimiter(sample: str) -> str:
    """Guess the delimiter; fall back to comma when sniffing fails."""
    candidates = [",", ";", "\t", "|"]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(candidates))
        if dialect.delimiter in candidates:
            return dialect.delimiter
    except csv.Error:
        pass
    return ","


def _decode(raw: bytes, encoding: str | None) -> tuple[str, str, bool, int]:
    """Decode bytes. Returns (text, encoding_used, fallback, replaced_chars)."""
    if encoding:
        try:
            return raw.decode(encoding), encoding, False, 0
        except LookupError:
            raise CsvLensError(f"Unknown encoding: '{encoding}'") from None
        except UnicodeDecodeError:
            text = raw.decode(encoding, errors="replace")
            replaced = text.count("�")
            return text, encoding, False, replaced or 1
    for enc in CANDIDATE_ENCODINGS:
        try:
            return raw.decode(enc), enc, enc != CANDIDATE_ENCODINGS[0], 0
        except UnicodeDecodeError:
            continue
    # latin-1 cannot fail, but guard anyway.
    text = raw.decode("latin-1", errors="replace")
    return text, "latin-1", True, text.count("�")


def load_csv(path: str, delimiter: str | None = None,
             encoding: str | None = None) -> LoadedCsv:
    """Load a CSV file into memory without modifying any value."""
    if not os.path.exists(path):
        raise CsvLensError(f"File not found: {path}")
    if not os.path.isfile(path):
        raise CsvLensError(f"Not a regular file: {path}")
    with open(path, "rb") as fh:
        raw = fh.read()
    if not raw:
        raise CsvLensError(f"File is empty (0 bytes): {path}")

    text, enc_used, fallback, replaced = _decode(raw, encoding)
    if not text.strip():
        raise CsvLensError(f"File contains no data rows: {path}")

    delim = delimiter or sniff_delimiter(text[:SNIFF_SAMPLE_BYTES])
    if len(delim) != 1:
        raise CsvLensError(
            f"Delimiter must be a single character, got {delim!r}.")
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        records = [rec for rec in reader if rec and any(c.strip() for c in rec)]
    except csv.Error as exc:
        raise CsvLensError(
            f"Could not parse {path} as CSV: {exc}. "
            f"Check that '{delim}' is the right delimiter "
            f"(override with --delimiter).") from None
    if not records:
        raise CsvLensError(f"File contains no parseable rows: {path}")

    headers = [h.strip() for h in records[0]]
    if not headers or all(h == "" for h in headers):
        raise CsvLensError(f"First row is not a usable header in: {path}")
    if len(headers) > MAX_COLUMNS:
        raise CsvLensError(
            f"Too many columns ({len(headers)} > {MAX_COLUMNS}); "
            f"is '{delim}' the right delimiter?")
    if len(set(headers)) != len(headers):
        # Rename duplicates deterministically so every column stays visible.
        seen: dict[str, int] = {}
        renamed = []
        for h in headers:
            seen[h] = seen.get(h, 0) + 1
            renamed.append(h if seen[h] == 1 else f"{h}__dup{seen[h]}")
        headers = renamed

    warnings: list[str] = []
    rows: list[list[str]] = []
    mismatches = 0
    width = len(headers)
    for rec in records[1:]:
        if len(rec) != width:
            mismatches += 1
        if len(rec) < width:
            rec = rec + [""] * (width - len(rec))
        rows.append(rec[:width])
    if mismatches:
        warnings.append(
            f"{mismatches} row(s) had a column count different from the "
            f"header; short rows were padded with empty strings and long "
            f"rows truncated for display (original file untouched).")
    if fallback:
        warnings.append(
            f"Encoding auto-detected as '{enc_used}' (file is not valid "
            f"UTF-8). Pass --encoding to override.")
    if replaced:
        warnings.append(
            f"{replaced} character(s) could not be decoded with '{enc_used}' "
            f"and were replaced with U+FFFD.")

    return LoadedCsv(
        path=path, headers=headers, rows=rows, delimiter=delim,
        encoding=enc_used, encoding_fallback=fallback,
        replaced_chars=replaced, row_length_mismatches=mismatches,
        warnings=warnings,
    )
