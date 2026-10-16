"""Reproduce disclosed external checkpoints without redistributing source PDFs."""

from __future__ import annotations

import argparse
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
    cases = json.loads((ROOT / "eval/public_cases.json").read_text())
    records = []
    for case in cases:
        path = args.cache / case["file"]
        if not path.exists():
            if not args.fetch:
                raise SystemExit(
                    f"Missing {path.name}; rerun with --fetch to download public fixtures."
                )
            with urlopen(case["url"], timeout=40) as response:
                content = response.read(40_000_001)
            if len(content) > 40_000_000:
                raise ValueError("Public fixture exceeds the bounded download size.")
            if hashlib.sha256(content).hexdigest() != case["sha256"]:
                raise ValueError("Upstream bytes differ from the pinned fixture.")
            path.write_bytes(content)
        if hashlib.sha256(path.read_bytes()).hexdigest() != case["sha256"]:
            raise ValueError(f"Checksum mismatch: {path.name}")
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
        "Three public aggregate/dummy PDFs, with source hashes and explicit annotation scope in `eval/public_cases.json`. Expectations were transcribed from rendered source pages, not independently annotated by a third party. These inputs were used to discover and repair failures; they are development regressions, not a blind benchmark. No source PDF or competitor implementation is redistributed.",
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
        "The fuel table checks all 35 data cells and seven flattened headers. The census page checks **48 selected data cells**, all 16 headers, both table counts/shapes (32×10 and 32×6), and uniqueness of selected row labels. Its other 464 data cells were not independently checked. The W3C fixture checks that no table is invented. Do not describe these checkpoints as whole-document OCR accuracy.",
        "",
        "The first saved development outputs failed the fuel table and census layouts; their measurements remain in the JSON when present. Header-span handling, numeric text-fragment joining and separated borderless streams were repaired with general geometry rules. The old engine state was not a tagged release; first observations are historical evidence, not a reproducible old-version benchmark.",
        "",
        "Unmapped text-layer glyphs, complex nested/merged body cells, handwriting and arbitrary damaged scans remain limitations. Inferred structure and header re-readings remain flagged.",
        "",
        "Reproduce: `python scripts/public_audit.py --fetch` on the first run, then omit `--fetch` for verified cached sources. This command makes network requests only with `--fetch`. The ordinary converter is offline unless cloud verification is explicitly enabled.",
        "",
    ]
    for case in cases:
        lines.append(f"- {case['name']}: {case['url']} (SHA-256 `{case['sha256']}`)")
    (ROOT / "reports/EXTERNAL_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "reports/EXTERNAL_AUDIT.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    return 0 if all(r["pass"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
