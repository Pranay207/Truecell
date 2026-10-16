"""Evaluate Truecell against explicitly supplied public dummy fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.score import score
from truecell.pipeline import convert


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--first-observations", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/transfer-audit")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    truth = json.loads((args.fixtures / "ground_truth.json").read_text(encoding="utf-8"))
    old = {}
    if args.first_observations:
        old = {r["case"]: r for r in json.loads(args.first_observations.read_text())}
    records = []
    for filename, expected in truth.items():
        source = args.fixtures / filename
        result = convert(source, args.output / (source.stem + ".xlsx"))
        target = {
            "name": filename,
            "pages": expected["pages"],
            "tables": [{"headers": expected["headers"], "rows": expected["rows"]}],
        }
        metric = score(target, result)
        records.append(
            {
                **metric,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "checked_data_cells": sum(map(len, expected["rows"])),
                "first_development_observation": old.get(filename),
            }
        )
        (args.output / (source.stem + ".audit.json")).write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )
        print(f"{filename}: exact={metric['cell_exact']:.2%}, pass={metric['pass']}", flush=True)
    lines = [
        "# External published-fixture audit",
        "",
        "This report evaluates only the Truecell engine against three public dummy PDFs and their "
        "author-provided expected results from "
        "[damnlens-ai-agent](https://github.com/rayanakarthikeyan/damnlens-ai-agent) at "
        "commit `9fb9116422ed4685e97ff8de6a95c01cc4788575`. The source repository's "
        "application code was not run, and its fixture files are not included in Truecell. "
        "Because these fixtures informed later development, the results are regression checks "
        "rather than a blind evaluation.",
        "",
        "| Fixture | Checked data cells | Exact cells | Headers | Shape | Result |",
        "|---|---:|---:|---:|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['case']} | {r['checked_data_cells']} | {r['cell_exact']:.2%} | "
            f"{r['header_match']:.2%} | {r['shape_match']} | {'PASS' if r['pass'] else 'FAIL'} |"
        )
    lines += [
        "",
        "Historical first observations, when supplied, are preserved in the JSON. "
        "The earlier engine state was not a tagged release; those measurements are historical, "
        "not a reproducible old-version comparison. Scoring canonicalizes numeric formatting "
        "and whitespace while requiring ordered table/row/column matches. "
        "Financial-source error recall is not scored here because this external truth file "
        "does not annotate injected errors.",
        "",
        "Reproduce after obtaining the public samples directory from the cited source: "
        "`python scripts/transfer_audit.py --fixtures PATH_TO_SAMPLES`. "
        "The audit script invokes only Truecell application code.",
        "",
    ]
    (ROOT / "reports/TRANSFER_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "reports/TRANSFER_AUDIT.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    return 0 if all(r["pass"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
