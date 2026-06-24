"""CLI: check a product catalog file against JD Union.

Usage:
    python -m src.cli_check_union INPUT.xlsx [-o REPORT.csv]

Reads JD SKU ids from item.jd.com/<sku>.html URLs in the file, queries JD
Union in batches, and writes a per-row CSV report (or prints a summary if no
output path is given). Works in mock mode without real credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from src.config import get_settings
from src.jd_union.catalog_check import check_products, load_product_file, report_to_csv


async def _run(input_path: str, output_path: str | None) -> int:
    rows = load_product_file(input_path)
    if not rows:
        print(f"No rows parsed from {input_path}", file=sys.stderr)
        return 1

    settings = get_settings()
    print(f"Parsed {len(rows)} rows, mode={settings.jd_union_mode}. Checking…", file=sys.stderr)
    report = await check_products(rows, settings=settings)

    s = report.summary()
    print(
        f"\nTotal: {s['total']}  |  with SKU: {s['with_sku']}  |  "
        f"found: {s['found']}  |  not found: {s['not_found']}  |  no SKU: {s['no_sku']}",
        file=sys.stderr,
    )

    if output_path:
        Path(output_path).write_text(report_to_csv(report), encoding="utf-8")
        print(f"Report written to {output_path}", file=sys.stderr)
    else:
        print(report_to_csv(report))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a catalog file against JD Union.")
    parser.add_argument("input", help="Path to .xlsx or .csv product file")
    parser.add_argument("-o", "--output", help="Path to write the CSV report")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.input, args.output)))


if __name__ == "__main__":
    main()
