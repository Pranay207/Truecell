"""Command-line interface with progress logging and machine-readable audit output."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .pipeline import convert
from .router import InputError


def main(argv: list[str] | None = None) -> int:
    """Convert one document and return a conventional process status."""
    parser = argparse.ArgumentParser(
        description="Truecell: PDF / scan to audited Excel, offline on CPU"
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--audit-json",
        type=Path,
        help="Also save extraction and attempt records as JSON",
    )
    parser.add_argument(
        "--no-recovery",
        action="store_true",
        help="Use only the first extraction strategy",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Cross-check native PDF pages with an independent OCR reading",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Read all pages through OCR, including PDFs with damaged text layers",
    )
    parser.add_argument(
        "--allow-cloud",
        action="store_true",
        help="Allow configured vision API requests for difficult pages; requires API configuration",
    )
    parser.add_argument(
        "--checkpoints",
        type=Path,
        help="Save/resume completed pages with verified source/code signatures",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    output = args.output or args.input.with_suffix(".xlsx")
    if args.input.resolve() == output.resolve():
        parser.error("Output must differ from input.")
    paths = [args.input.resolve(), output.resolve()]
    if args.audit_json:
        paths.append(args.audit_json.resolve())
    if len(set(paths)) != len(paths):
        parser.error("Source, Excel output and JSON audit must have distinct paths.")
    if output.suffix.lower() != ".xlsx":
        parser.error("Excel output must use the .xlsx extension.")
    try:
        result = convert(
            args.input,
            output,
            recover=not args.no_recovery,
            verify=args.verify,
            force_ocr=args.force_ocr,
            checkpoint_dir=args.checkpoints,
            allow_cloud=args.allow_cloud,
        )
        if args.audit_json:
            args.audit_json.parent.mkdir(parents=True, exist_ok=True)
            args.audit_json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    except (InputError, OSError, ValueError) as exc:
        logging.error("%s", exc)
        return 2
    print(
        f"Saved {output}: {len(result.tables)} tables, "
        f"{sum(len(t.rows) for t in result.tables)} rows, {len(result.issues)} findings, {result.seconds:.2f}s"
    )
    return 0 if result.tables else 3
