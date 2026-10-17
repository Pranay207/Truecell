"""Reproduce disclosed external checkpoints without redistributing source PDFs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.score import canonical, score
from truecell.models import Result
from truecell.pipeline import convert

MAX_FIXTURE_BYTES = 40_000_000


def materialize(path: Path, url: str, expected_sha256: str, fetch: bool) -> None:
    """Download an explicitly requested public artifact and verify its pinned bytes."""
    if not path.exists():
        if not fetch:
            raise SystemExit(
                f"Missing {path.name}; rerun with --fetch to download public fixtures."
            )
        with urlopen(url, timeout=40) as response:
            content = response.read(MAX_FIXTURE_BYTES + 1)
        if len(content) > MAX_FIXTURE_BYTES:
            raise ValueError("Public fixture exceeds the bounded download size.")
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise ValueError("Upstream bytes differ from the pinned fixture.")
        path.write_bytes(content)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError(f"Checksum mismatch: {path.name}")


def verify_tabula_twotables_reference(case: dict, path: Path) -> None:
    """Bind the embedded structured truth to Tabula's published CSV rows."""
    rows = list(csv.reader(path.open(encoding="utf-8-sig", newline="")))
    expected_blocks = (rows[2:11], rows[13:22])
    if len(case["tables"]) != 2 or any(len(block) != 9 for block in expected_blocks):
        raise ValueError("Unexpected Tabula twotables reference structure.")
    for table, reference_rows in zip(case["tables"], expected_blocks):
        if len(table["rows"]) != len(reference_rows):
            raise ValueError("Embedded truth does not match the published reference rows.")
        for expected, published in zip(table["rows"], reference_rows):
            # One visually identical parenthesis has different width metadata.
            normalized_expected = [canonical(value).replace("（", "(") for value in expected]
            normalized_published = [canonical(value).replace("（", "(") for value in published]
            if normalized_expected != normalized_published:
                raise ValueError("Embedded truth differs from Tabula's published CSV.")


def check(case: dict, result: Result) -> dict:
    if case["mode"] == "empty":
        return {
            "pass": not result.tables,
            "checked_cells": 0,
            "matching_cells": 0,
            "headers_match": True,
            "shape_match": not result.tables,
        }
    if case["mode"] == "full":
        metric = score({"name": case["name"], "pages": 1, "tables": case["tables"]}, result)
        cells = sum(len(row) for t in case["tables"] for row in t["rows"])
        return {
            "pass": metric["pass"],
            "checked_cells": cells,
            "matching_cells": round(
                metric["cell_exact"]
                * max(cells, sum(len(row) for t in result.tables for row in t.rows))
            ),
            "headers_match": metric["header_match"] == 1,
            "shape_match": metric["shape_match"],
        }
    matched = checked = 0
    headers = True
    shape = len(result.tables) == len(case["tables"])
    for ti, target in enumerate(case["tables"]):
        checked += sum(len(row) for row in target["rows"])
        if ti >= len(result.tables):
            headers = False
            shape = False
            continue
        table = result.tables[ti]
        headers &= table.headers == target["headers"]
        shape &= len(table.rows) == target["row_count"] and all(
            len(r) == len(target["headers"]) for r in table.rows
        )
        for expected in target["rows"]:
            hits = [
                row for row in table.rows if row and canonical(row[0]) == canonical(expected[0])
            ]
            if len(hits) == 1:
                matched += sum(canonical(a) == canonical(b) for a, b in zip(hits[0], expected))
    return {
        "pass": matched == checked and headers and shape,
        "checked_cells": checked,
        "matching_cells": matched,
        "headers_match": headers,
        "shape_match": shape,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/public-audit")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    cases = json.loads((ROOT / "eval/public_cases.json").read_text(encoding="utf-8"))
    records = []
    for case in cases:
        path = args.cache / case["file"]
        materialize(path, case["url"], case["sha256"], args.fetch)
        reference_path = None
        if case.get("reference_url"):
            reference_path = args.cache / case["reference_file"]
            materialize(
                reference_path,
                case["reference_url"],
                case["reference_sha256"],
                args.fetch,
            )
        if case["name"] == "tabula-unicode-two-tables" and reference_path:
            verify_tabula_twotables_reference(case, reference_path)
        result = convert(path, args.cache / (path.stem + "-truecell.xlsx"))
        (args.cache / (path.stem + "-latest.json")).write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )
        metric = check(case, result)
        first_path = args.cache / (path.stem + "-first.json")
        first = (
            check(case, Result.from_dict(json.loads(first_path.read_text(encoding="utf-8"))))
            if first_path.exists()
            else None
        )
        record = {
            "case": case["name"],
            "scope": case["mode"],
            "source_sha256": case["sha256"],
            "url": case["url"],
            "reference_url": case.get("reference_url"),
            "reference_sha256": case.get("reference_sha256"),
            "published_reference_verified": reference_path is not None,
            "seconds": result.seconds,
            "first_development_observation": first,
            **metric,
        }
        records.append(record)
        print(
            f"{'PASS' if metric['pass'] else 'FAIL'} {case['name']}: {metric['matching_cells']}/{metric['checked_cells']} checked cells",
            flush=True,
        )
    lines = [
        "# External document audit",
        "",
        f"{len(cases)} public aggregate/dummy PDFs from three independently maintained source projects, with source hashes and explicit annotation scope in `eval/public_cases.json`. Expectations were transcribed from rendered source pages; the Unicode two-table case is also bound to its publisher's paired CSV by checksum and an exact row comparison. These inputs were used to discover and repair failures, so they are development regressions rather than a blind benchmark. No source PDF or external application implementation is redistributed.",
        "",
        "| Case | Scope | Checked cells | Headers | Shape | Result |",
        "|---|---|---:|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['case']} | {r['scope']} | {r['matching_cells']}/{r['checked_cells']} | {r['headers_match']} | {r['shape_match']} | {'PASS' if r['pass'] else 'FAIL'} |"
        )
    lines += [
        "",
        "The fuel table checks all 35 data cells and seven flattened headers. The census page checks **48 selected data cells**, all 16 headers, both table counts/shapes (32×10 and 32×6), and uniqueness of selected row labels; its other 464 data cells are outside the annotation scope. The Unicode case checks two complete tables: all **126 data cells**, all 14 flattened headers, both shapes, Japanese text, multiline cells, spanning headers, and negative-triangle notation. The W3C fixture checks that no table is invented. Do not describe these checks as whole-document OCR accuracy.",
        "",
        "The first saved development outputs failed the fuel table and census layouts; their measurements remain in the JSON when present. Header-span handling, numeric text-fragment joining and separated borderless streams were repaired with general geometry rules. The old engine state was not a tagged release; first observations are historical evidence, not a reproducible old-version benchmark.",
        "",
        "Unmapped text-layer glyphs, handwriting and arbitrary damaged scans remain limitations. Explicitly ruled vertical group spans in native-PDF body rows are supported conservatively; OCR/unruled spans and arbitrary multi-axis nested merges remain ambiguous. Inferred structure and header re-readings remain flagged.",
        "",
        "Reproduce: `python scripts/public_audit.py --fetch` on the first run, then omit `--fetch` for verified cached sources. This command makes network requests only with `--fetch`. The ordinary converter is offline unless cloud verification is explicitly enabled.",
        "",
    ]
    for case in cases:
        lines.append(f"- {case['name']}: {case['url']} (SHA-256 `{case['sha256']}`)")
        if case.get("reference_url"):
            lines.append(
                f"  - Published reference CSV: {case['reference_url']} "
                f"(SHA-256 `{case['reference_sha256']}`)"
            )
    (ROOT / "reports/EXTERNAL_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "reports/EXTERNAL_AUDIT.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    return 0 if all(r["pass"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
