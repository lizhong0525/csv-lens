"""Command-line interface: `python -m csv_lens profile|diff ...`."""

from __future__ import annotations

import argparse
import os
import sys

from .compare import compare_csv
from .io import CsvLensError, load_csv
from .profile import profile_csv
from .report import (diff_to_dict, profile_to_dict, render_diff_report,
                     render_profile_report, write_json)


def _add_io_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--delimiter", default=None,
                   help="Column delimiter (default: auto-sniff).")
    p.add_argument("--encoding", default=None,
                   help="File encoding (default: auto-detect).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv-lens",
        description="Local-first CSV data-quality profiler and differ. "
                    "No data ever leaves your machine.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("profile", help="Profile a single CSV file.")
    p.add_argument("csv_file")
    _add_io_args(p)
    p.add_argument("--html", default=None,
                   help="Write interactive HTML report to this path "
                        "(default: <file>.report.html).")
    p.add_argument("--json", dest="json_path", default=None,
                   help="Also write a JSON summary to this path.")

    d = sub.add_parser("diff", help="Compare two CSV versions.")
    d.add_argument("old_csv")
    d.add_argument("new_csv")
    d.add_argument("--key", required=True,
                   help="Column uniquely identifying rows across versions.")
    _add_io_args(d)
    d.add_argument("--html", default=None,
                   help="Write HTML diff report to this path "
                        "(default: <old>.vs.<new>.diff.html).")
    d.add_argument("--json", dest="json_path", default=None,
                   help="Also write a JSON summary to this path.")
    return parser


def _cmd_profile(args: argparse.Namespace) -> int:
    data = load_csv(args.csv_file, delimiter=args.delimiter,
                    encoding=args.encoding)
    profile = profile_csv(data)
    html_path = args.html or args.csv_file + ".report.html"
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_profile_report(profile, data))
    print(f"HTML report:  {html_path}")
    if args.json_path:
        write_json(profile_to_dict(profile, data), args.json_path)
        print(f"JSON summary: {args.json_path}")

    print(f"\n{data.path}: {profile.n_rows} rows x {len(profile.headers)} columns "
          f"(encoding {data.encoding}, delimiter '{data.delimiter}')")
    for c in profile.columns:
        flags = []
        if c.missing_count:
            flags.append(f"{c.missing_count} missing")
        if c.mixed_type_suspicious:
            flags.append("mixed types")
        if c.high_cardinality:
            flags.append("high cardinality")
        if c.outlier_count:
            flags.append(f"{c.outlier_count} outlier candidates")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  {c.name:<20} {c.inferred_type:<8} "
              f"distinct={c.distinct_count:<6}{suffix}")
    if profile.duplicate_row_count:
        print(f"  duplicate full rows: {profile.duplicate_row_count}")
    for w in profile.warnings:
        print(f"  warning: {w}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    old = load_csv(args.old_csv, delimiter=args.delimiter, encoding=args.encoding)
    new = load_csv(args.new_csv, delimiter=args.delimiter, encoding=args.encoding)
    diff = compare_csv(old, new, key=args.key)
    base_old = os.path.basename(args.old_csv).rsplit(".", 1)[0]
    base_new = os.path.basename(args.new_csv).rsplit(".", 1)[0]
    html_path = args.html or os.path.join(
        os.path.dirname(os.path.abspath(args.old_csv)),
        f"{base_old}.vs.{base_new}.diff.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_diff_report(diff, old, new))
    print(f"HTML report:  {html_path}")
    if args.json_path:
        write_json(diff_to_dict(diff), args.json_path)
        print(f"JSON summary: {args.json_path}")

    s = diff.schema
    print(f"\nSchema: +{len(s.added_columns)} columns {s.added_columns or ''} "
          f"-{len(s.removed_columns)} columns {s.removed_columns or ''} "
          f"reordered={s.reordered}")
    print(f"Rows (key '{diff.key_column}'): {len(diff.added_rows)} added, "
          f"{len(diff.removed_rows)} removed, {len(diff.changed_cells)} cells changed")
    if diff.duplicate_keys_old or diff.duplicate_keys_new:
        print(f"  duplicate keys: old={diff.duplicate_keys_old} "
              f"new={diff.duplicate_keys_new}")
    for c in diff.changed_cells[:10]:
        print(f"  {c.key} | {c.column}: {c.old_value!r} -> {c.new_value!r}")
    if len(diff.changed_cells) > 10:
        print(f"  ... and {len(diff.changed_cells) - 10} more (see report)")
    for w in diff.warnings:
        print(f"  warning: {w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "profile":
            return _cmd_profile(args)
        return _cmd_diff(args)
    except CsvLensError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: could not read/write file: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
