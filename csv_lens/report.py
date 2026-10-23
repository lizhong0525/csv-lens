"""HTML report and JSON summary generation. Fully offline, self-contained."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime, timezone

from .compare import DiffResult
from .io import LoadedCsv
from .profile import (HIGH_CARDINALITY_RATIO, MIXED_TYPE_MINORITY,
                      OUTLIER_IQR_FACTOR, Profile)

MAX_PREVIEW_ROWS = 500

STYLE = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem auto;
max-width:1100px;padding:0 1rem;color:#1a1a1a;background:#fafafa}
h1{border-bottom:3px solid #2563eb;padding-bottom:.3rem}
h2{margin-top:2rem;color:#1e40af}
table{border-collapse:collapse;width:100%;font-size:.9rem;background:#fff}
th,td{border:1px solid #d4d4d4;padding:.35rem .6rem;text-align:left;vertical-align:top}
th{background:#eff6ff;cursor:pointer;user-select:none}
tr:nth-child(even){background:#f5f7fa}
.badge{display:inline-block;padding:.1rem .5rem;border-radius:.6rem;font-size:.75rem}
.warn{background:#fef3c7;color:#92400e}.bad{background:#fee2e2;color:#991b1b}
.ok{background:#dcfce7;color:#166534}.info{background:#dbeafe;color:#1e40af}
.meta{color:#555;font-size:.85rem}
input[type=search]{padding:.4rem .6rem;width:16rem;border:1px solid #bbb;border-radius:.4rem}
.card{background:#fff;border:1px solid #e2e2e2;border-radius:.5rem;padding:1rem;margin:.6rem 0}
footer{margin-top:3rem;color:#888;font-size:.8rem}
"""

SCRIPT = """
function sortTable(t,i){const b=t.tBodies[0];const r=[...b.rows];
const asc=t.dataset.sortCol!=i||t.dataset.sortDir=='desc';
r.sort((a,b)=>{const x=a.cells[i].innerText,y=b.cells[i].innerText;
const n=parseFloat(x)-parseFloat(y);
const c=isNaN(n)?x.localeCompare(y):n;return asc?c:-c});
r.forEach(x=>b.appendChild(x));t.dataset.sortCol=i;t.dataset.sortDir=asc?'asc':'desc'}
document.querySelectorAll('table.sortable').forEach(t=>{
[...t.tHead.rows[0].cells].forEach((c,i)=>c.addEventListener('click',()=>sortTable(t,i)))});
function filterTable(id,q){q=q.toLowerCase();document.querySelectorAll('#'+id+' tbody tr')
.forEach(r=>r.style.display=r.innerText.toLowerCase().includes(q)?'':'none')}
"""


def _esc(s: object) -> str:
    return html.escape(str(s))


def _badge(text: str, kind: str) -> str:
    return f'<span class="badge {kind}">{_esc(text)}</span>'


def _table(headers: list[str], rows: list[list[object]],
           sortable: bool = True, table_id: str = "") -> str:
    cls = ' class="sortable"' if sortable else ""
    idattr = f' id="{table_id}"' if table_id else ""
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>"
        for r in rows)
    return f"<table{cls}{idattr}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title><style>{STYLE}</style></head><body>"
        f"<h1>{_esc(title)}</h1>{body}"
        f"<script>{SCRIPT}</script>"
        "<footer>Generated locally by csv-lens. No data ever leaves this "
        "machine. Statistical outliers are review candidates, not "
        "necessarily errors.</footer></body></html>")


def profile_to_dict(profile: Profile, data: LoadedCsv) -> dict:
    return {
        "file": data.path,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "encoding": data.encoding,
        "encoding_fallback": data.encoding_fallback,
        "replaced_chars": data.replaced_chars,
        "delimiter": data.delimiter,
        "rows": profile.n_rows,
        "columns": len(profile.headers),
        "duplicate_rows": profile.duplicate_row_count,
        "warnings": profile.warnings,
        "rules": {
            "outliers": f"{OUTLIER_IQR_FACTOR}*IQR fences (review candidates, not errors)",
            "mixed_type": f"minority type share >= {MIXED_TYPE_MINORITY:.0%} of present values",
            "high_cardinality": f"distinct/present >= {HIGH_CARDINALITY_RATIO:.0%}",
        },
        "column_profiles": [asdict(c) for c in profile.columns],
    }


def diff_to_dict(diff: DiffResult) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "key_column": diff.key_column,
        "schema": asdict(diff.schema),
        "added_rows": diff.added_rows,
        "removed_rows": diff.removed_rows,
        "changed_cells": [asdict(c) for c in diff.changed_cells],
        "duplicate_keys_old": diff.duplicate_keys_old,
        "duplicate_keys_new": diff.duplicate_keys_new,
        "warnings": diff.warnings,
    }


def write_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)


def _column_section(profile: Profile) -> str:
    rows = []
    for c in profile.columns:
        stats = ""
        if c.numeric:
            stats = (f"min {c.numeric['min']:g} · max {c.numeric['max']:g} · "
                     f"mean {c.numeric['mean']:g} · median {c.numeric['median']:g}")
        flags = []
        if c.mixed_type_suspicious:
            flags.append(_badge("mixed types", "warn"))
        if c.high_cardinality:
            flags.append(_badge("high cardinality", "info"))
        if c.missing_count:
            flags.append(_badge(f"{c.missing_count} missing ({c.missing_pct:.1f}%)",
                                "warn" if c.missing_pct < 20 else "bad"))
        if c.outlier_count:
            flags.append(_badge(f"{c.outlier_count} outlier candidates", "info"))
        rows.append([c.name, c.inferred_type,
                     ", ".join(f"{t}:{n}" for t, n in sorted(c.type_counts.items())),
                     c.distinct_count, f"{c.cardinality_ratio:.2f}",
                     stats, " ".join(flags)])
    return "<h2>Columns</h2>" + _table(
        ["column", "inferred type", "type counts", "distinct", "distinct ratio",
         "numeric summary", "flags"], rows)


def _issues_section(profile: Profile) -> str:
    parts = ["<h2>Data quality findings</h2>"]
    if profile.warnings:
        parts.append("<div class='card'>" + "<br>".join(
            _badge("warning", "warn") + " " + _esc(w)
            for w in profile.warnings) + "</div>")
    if profile.duplicate_row_count:
        parts.append(f"<p>{_badge('duplicate rows', 'bad')} "
                     f"{profile.duplicate_row_count} duplicated row(s) "
                     f"(exact full-row duplicates) found. Nothing was removed.</p>")
        parts.append(_table(["example duplicate row"],
                            [[", ".join(r)] for r in profile.duplicate_row_examples],
                            sortable=False))
    outlier_rows = []
    for c in profile.columns:
        for row_idx, val in c.outliers:
            outlier_rows.append([c.name, row_idx + 2, val])  # +2: header + 1-based
    if outlier_rows:
        parts.append(f"<p>{_badge('outliers', 'info')} Outlier candidates by the "
                     f"{OUTLIER_IQR_FACTOR}*IQR fence rule. These are review "
                     f"candidates, not necessarily errors.</p>")
        parts.append(_table(["column", "row # (in file)", "value"], outlier_rows))
    mixed = [c for c in profile.columns if c.mixed_type_suspicious]
    if mixed:
        parts.append(f"<p>{_badge('mixed types', 'warn')} Columns with "
                     f"suspicious mixed types: "
                     + ", ".join(_esc(c.name) for c in mixed) + "</p>")
    if not (profile.warnings or profile.duplicate_row_count or outlier_rows or mixed):
        parts.append(f"<p>{_badge('clean', 'ok')} No findings beyond basic statistics.</p>")
    return "".join(parts)


def _categories_section(profile: Profile) -> str:
    parts = []
    for c in profile.columns:
        if c.top_categories:
            total = sum(n for _, n in c.top_categories) or 1
            rows = [[v if v else "(empty)", n, f"{100*n/total:.1f}%"]
                    for v, n in c.top_categories]
            parts.append(f"<h3>{_esc(c.name)}</h3>"
                         + _table(["value", "count", "share"], rows))
    if not parts:
        return ""
    return "<h2>Category distributions</h2>" + "".join(parts)


def _preview_section(data: LoadedCsv) -> str:
    shown = data.rows[:MAX_PREVIEW_ROWS]
    note = (f"Showing first {len(shown)} of {data.n_rows} rows."
            if data.n_rows > len(shown) else f"All {data.n_rows} rows shown.")
    return (f"<h2>Data preview</h2><p class='meta'>{_esc(note)} "
            "Click a header to sort.</p>"
            '<input type="search" placeholder="Filter rows..." '
            'oninput="filterTable(\'preview\',this.value)">'
            + _table(["#"] + data.headers,
                     [[i + 2] + r for i, r in enumerate(shown)],
                     table_id="preview"))


def render_profile_report(profile: Profile, data: LoadedCsv) -> str:
    meta = (f"<p class='meta'>File: {_esc(data.path)} · encoding "
            f"{_esc(data.encoding)}{' (auto-detected)' if data.encoding_fallback else ''}"
            f" · delimiter '{_esc(data.delimiter)}' · {profile.n_rows} rows × "
            f"{len(profile.headers)} columns · "
            f"{profile.duplicate_row_count} duplicate rows</p>")
    body = (meta + _column_section(profile) + _issues_section(profile)
            + _categories_section(profile) + _preview_section(data))
    return _page("csv-lens profile report", body)


def render_diff_report(diff: DiffResult, old: LoadedCsv, new: LoadedCsv) -> str:
    s = diff.schema
    meta = (f"<p class='meta'>Old: {_esc(old.path)} ({old.n_rows} rows) · "
            f"New: {_esc(new.path)} ({new.n_rows} rows) · key column "
            f"'{_esc(diff.key_column)}'</p>")
    parts = [meta, "<h2>Schema diff</h2>"]
    schema_rows = [
        ["added columns", ", ".join(s.added_columns) or "—"],
        ["removed columns", ", ".join(s.removed_columns) or "—"],
        ["column order changed", "yes" if s.reordered else "no"],
        ["common columns", len(s.common_columns)],
    ]
    parts.append(_table(["aspect", "value"], schema_rows, sortable=False))
    for w in diff.warnings:
        parts.append(f"<p>{_badge('warning', 'warn')} {_esc(w)}</p>")
    if diff.duplicate_keys_old or diff.duplicate_keys_new:
        parts.append(f"<p>{_badge('duplicate keys', 'bad')} Duplicate keys — "
                     f"old: {_esc(', '.join(diff.duplicate_keys_old) or 'none')}; "
                     f"new: {_esc(', '.join(diff.duplicate_keys_new) or 'none')}</p>")
    parts.append(f"<h2>Added rows ({len(diff.added_rows)})</h2>")
    parts.append(_table(new.headers, diff.added_rows) if diff.added_rows
                 else "<p>None.</p>")
    parts.append(f"<h2>Removed rows ({len(diff.removed_rows)})</h2>")
    parts.append(_table(old.headers, diff.removed_rows) if diff.removed_rows
                 else "<p>None.</p>")
    parts.append(f"<h2>Changed cells ({len(diff.changed_cells)})</h2>")
    if diff.changed_cells:
        parts.append(_table(["key", "column", "old value", "new value"],
                            [[c.key, c.column, c.old_value, c.new_value]
                             for c in diff.changed_cells]))
    else:
        parts.append("<p>None.</p>")
    return _page("csv-lens diff report", "".join(parts))
