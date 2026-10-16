"""Score independent truth against raw extraction, including missing/extra tables."""

from __future__ import annotations

import argparse
import json
import platform
from collections import Counter
from pathlib import Path

from truecell.models import Result
from truecell.pipeline import convert
from truecell.values import is_identifier, number

ROOT = Path(__file__).resolve().parents[1]


def canonical(value: object) -> str:
    """Normalize harmless whitespace and numeric display, preserving identifiers."""
    text = " ".join(str(value).split())
    parsed = number(text)
    if parsed is not None and not is_identifier(text):
        return str(parsed.normalize()) if parsed else "0"
    return text


def score(truth: dict, result: Result) -> dict:
    """Compute coordinate-sensitive metrics; duplicates count with multiplicity."""
    expected, actual = truth["tables"], result.tables
    expected_cells = sum(len(row) for t in expected for row in t["rows"])
    actual_cells = sum(len(row) for t in actual for row in t.rows)
    matches = header_matches = header_count = matched_rows = 0
    expected_rows = sum(len(t["rows"]) for t in expected)
    for ti, target in enumerate(expected):
        header_count += len(target["headers"])
        if ti >= len(actual):
            continue
        candidate = actual[ti]
        header_matches += sum(
            canonical(a) == canonical(b) for a, b in zip(target["headers"], candidate.headers)
        )
        target_counts = Counter(tuple(canonical(v) for v in row) for row in target["rows"])
        actual_counts = Counter(tuple(canonical(v) for v in row) for row in candidate.rows)
        matched_rows += sum((target_counts & actual_counts).values())
        for ri, row in enumerate(target["rows"]):
            if ri >= len(candidate.rows):
                continue
            matches += sum(canonical(a) == canonical(b) for a, b in zip(row, candidate.rows[ri]))
    shape = len(expected) == len(actual) and all(
        len(t["headers"]) == len(a.headers)
        and len(t["rows"]) == len(a.rows)
        and all(len(r) == len(t["headers"]) for r in a.rows)
        for t, a in zip(expected, actual)
    )
    caught = 0
    for error in truth.get("injected_errors", []):
        table_no = error["table"]
        if table_no > len(actual) or error["row"] > len(actual[table_no - 1].provenance):
            continue
        sources = actual[table_no - 1].provenance[error["row"] - 1]
        caught += any(
            i.table == table_no
            and (i.page, i.row) in sources
            and i.column == error["column"]
            and i.code == error["code"]
            for i in result.issues
        )
    return {
        "case": truth["name"],
        "expected_cells": expected_cells,
        "precision": matches / max(1, actual_cells),
        "recall": matches / max(1, expected_cells),
        "cell_exact": matches / max(1, expected_cells, actual_cells),
        "row_match": matched_rows / max(1, expected_rows),
        "header_match": header_matches / max(1, header_count),
        "shape_match": shape,
        "tables_count_match": len(expected) == len(actual),
        "errors_caught": caught,
        "errors_injected": len(truth.get("injected_errors", [])),
        "seconds": result.seconds,
        "seconds_per_page": result.seconds / max(1, truth["pages"]),
        "findings": len(result.issues),
        "pass": shape
        and matches == expected_cells == actual_cells
        and header_matches == header_count
        and caught == len(truth.get("injected_errors", [])),
    }


def write_report(metrics: list[dict], output: Path) -> None:
    """Publish measured development-set results and explicit limitations."""
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Accuracy and validation report",
        "",
        "Measured on deterministic, self-generated dummy development documents. These numbers are not independent benchmarks and do not guarantee hidden-PDF accuracy.",
        "",
        "Cell precision/recall compare canonicalized values at exact table/row/column coordinates. Numeric formatting and whitespace are normalized; leading zeros are preserved. Row match uses a multiset, so duplicate records are counted. PASS requires exact cells, headers, shape and detection of every injected error.",
        "No-table controls show n/a for cell/row/header percentages; passing requires no extra table. They do not contribute fabricated cell matches.",
        "",
        f"Evaluation host: Python {platform.python_version()}, {platform.system()} {platform.machine()}. Timings are local wall-clock measurements and can include concurrent system activity. Peak memory was not benchmarked.",
        "",
        "| Problem case | Cell P | Cell R | Exact | Rows | Headers | Shape | Tables | Errors caught | s/page | Result |",
        "|---|---:|---:|---:|---:|---:|---|---|---|---:|---|",
    ]
    for m in metrics:
        cells = [
            f"{m[k]:.1%}"
            for k in ("precision", "recall", "cell_exact", "row_match", "header_match")
        ]
        if m.get("expected_cells") == 0:
            cells = ["n/a"] * 5
        lines.append(
            f"| {m['case']} | {' | '.join(cells)} | {m['shape_match']} | {m['tables_count_match']} | {m['errors_caught']}/{m['errors_injected']} | {m['seconds_per_page']:.2f} | {'PASS' if m['pass'] else 'FAIL'} |"
        )
    lines += [
        "",
        "## Known limitations / failures",
        "",
        "- OCR confidence is not a calibrated accuracy probability. High-confidence digit mistakes can still occur.",
        "- Explicitly ruled vertical group spans in native-PDF body rows are supported conservatively. OCR/unruled spans, arbitrary multi-axis nested merges, borderless segmentation, two unrelated tables with similar geometry, and cross-page wrapped records can remain ambiguous. Values are retained for review; no business-row deduplication is performed.",
        "- Arithmetic inference needs enough varied rows and a strong majority. Checks may be skipped on short/heterogeneous tables. Inferred relations can be coincidental. Candidate selection prioritizes trusted native grid geometry but can still select the wrong layout; disagreements are audited.",
        "- Ambiguous day/month dates and comma-decimal numeric strings remain text. Structural total inference and multilingual total vocabularies are limited.",
        "- Phone-photo perspective, extreme rotation and handwritten text are not guaranteed.",
        "- The optional network vision pass requires explicit configuration AND opt-in and is not part of offline baseline metrics.",
        "",
    ]
    from truecell.ocr import available_engines

    lines += [
        "Available OCR engines in this run: "
        + ", ".join(available_engines())
        + ". Page Audit records which was selected. A machine with only RapidOCR can produce different accuracy and runtime.",
        "",
        "The bank sample contains two injected source errors. An altered balance can raise findings on both the altered row and its successor because each printed balance is checked against the previous printed balance. Review findings also include expected layout/uncertainty notices and are not a count of proven extraction errors.",
        "Source-cell boxes, equation receipts, and counterfactual repair proposals are exported alongside the data. No proposal is applied in this benchmark. Header re-readings remain flagged even when they improve transcription. Human review status starts as Unreviewed.",
        "",
        "The separate Challenge lab deliberately perturbs numeric cells in copies of this extraction and reports detected AND missed edits. It tests validation sensitivity, not OCR accuracy; unmodeled columns can miss every edit.",
        "",
    ]
    failures = [m["case"] for m in metrics if not m["pass"]]
    lines.append(
        "Observed failing cases: "
        + (", ".join(failures) if failures else "none in this evaluated subset")
        + "."
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output.with_suffix(".json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def run(samples: Path, destination: Path, selected: str = "*") -> list[dict]:
    """Convert each selected source and save matching Excel and audit outputs."""
    metrics = []
    destination.mkdir(parents=True, exist_ok=True)
    for truth_file in sorted(samples.glob(f"{selected}.truth.json")):
        truth = json.loads(truth_file.read_text(encoding="utf-8"))
        name = truth["name"]
        result = convert(samples / f"{name}.pdf", destination / f"{name}.xlsx")
        (destination / f"{name}.audit.json").write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )
        metric = score(truth, result)
        metrics.append(metric)
        print(
            f"{'PASS' if metric['pass'] else 'FAIL'} {name}: exact="
            + (f"{metric['cell_exact']:.2%}" if truth["tables"] else "n/a (no-table control)")
            + ", "
            + f"rows={metric['row_match']:.2%}, errors={metric['errors_caught']}/{metric['errors_injected']}, {result.seconds:.2f}s",
            flush=True,
        )
    return metrics


def main() -> None:
    """Run repeatable development evaluation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=ROOT / "samples")
    parser.add_argument("--outputs", type=Path, default=ROOT / "outputs")
    parser.add_argument("--case", default="*")
    args = parser.parse_args()
    metrics = run(args.samples, args.outputs, args.case)
    if not metrics:
        raise SystemExit("No ground-truth files matched.")
    write_report(metrics, ROOT / "reports" / "ACCURACY_REPORT.md")


if __name__ == "__main__":
    main()
