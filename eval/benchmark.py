"""Two-stage, source-bound evaluation for genuinely held-out documents.

The extraction stage never needs access to truth.  An evaluator can provide
truth later and score the saved audit without running the extractor again.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.score import score
from truecell.constraints import coverage
from truecell.models import Result
from truecell.pipeline import convert

CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


class ManifestError(ValueError):
    """The benchmark manifest is unsafe or incomplete."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(root: Path, name: str) -> Path:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ManifestError(f"Benchmark path must stay inside its pack: {name!r}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ManifestError(f"Benchmark path escapes its pack: {name!r}")
    return resolved


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cannot read benchmark manifest: {exc}") from exc
    if manifest.get("version") != 1 or not isinstance(manifest.get("cases"), list):
        raise ManifestError("Manifest must use version 1 and contain a cases list.")
    seen: set[str] = set()
    for case in manifest["cases"]:
        if not isinstance(case, dict):
            raise ManifestError("Every benchmark case must be an object.")
        identifier = case.get("id")
        if not isinstance(identifier, str) or not CASE_ID.fullmatch(identifier):
            raise ManifestError(f"Unsafe or missing case id: {identifier!r}")
        if identifier in seen:
            raise ManifestError(f"Duplicate benchmark case id: {identifier}")
        seen.add(identifier)
        if not isinstance(case.get("file"), str):
            raise ManifestError(f"Case {identifier} has no input file.")
        expected_hash = case.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ManifestError(f"Case {identifier} needs a lowercase SHA-256 hash.")
        if "truth" in case and not isinstance(case["truth"], str):
            raise ManifestError(f"Case {identifier} truth path must be a string.")
    return manifest


def extract_manifest(manifest_path: Path, inputs: Path, output: Path) -> dict[str, Any]:
    """Convert a held-out pack while keeping truth outside the process."""
    manifest = load_manifest(manifest_path)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for case in manifest["cases"]:
        identifier = case["id"]
        source = _relative(inputs, case["file"])
        if not source.is_file():
            raise ManifestError(f"Missing benchmark input for {identifier}: {source.name}")
        observed_hash = sha256(source)
        if observed_hash != case["sha256"]:
            raise ManifestError(f"Input hash mismatch for {identifier}.")
        result = convert(source, output / f"{identifier}.xlsx")
        audit_path = output / f"{identifier}.audit.json"
        audit_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        records.append(
            {
                "id": identifier,
                "category": case.get("category", "unspecified"),
                "language": case.get("language", "unspecified"),
                "source_sha256": observed_hash,
                "pages": len(result.pages),
                "tables": len(result.tables),
                "rows": sum(len(table.rows) for table in result.tables),
                "cells": sum(len(row) for table in result.tables for row in table.rows),
                "findings": len(result.issues),
                "failed_pages": sum(bool(page.error) for page in result.pages),
                "seconds": result.seconds,
                "evidence": coverage(result),
                "audit": audit_path.name,
                "workbook": f"{identifier}.xlsx",
            }
        )
    run = {
        "suite": manifest.get("suite", manifest_path.stem),
        "manifest_sha256": sha256(manifest_path),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "truth_available_during_extraction": False,
        "cases": records,
    }
    (output / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    return run


def score_saved(manifest_path: Path, output: Path, truth_root: Path) -> list[dict[str, Any]]:
    """Score saved audits; never rerun or mutate the extraction."""
    manifest = load_manifest(manifest_path)
    run_path = output / "run.json"
    if not run_path.is_file():
        raise ManifestError("Missing run.json; perform the extraction stage first.")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("manifest_sha256") != sha256(manifest_path):
        raise ManifestError("Manifest changed after extraction; start a new benchmark run.")
    records_by_id = {record["id"]: record for record in run.get("cases", [])}
    metrics = []
    for case in manifest["cases"]:
        identifier = case["id"]
        record = records_by_id.get(identifier)
        if record is None or record.get("source_sha256") != case["sha256"]:
            raise ManifestError(f"Saved run is missing or mismatched for {identifier}.")
        truth_name = case.get("truth", f"{identifier}.truth.json")
        truth_path = _relative(truth_root, truth_name)
        audit_path = _relative(output, record["audit"])
        if not truth_path.is_file() or not audit_path.is_file():
            raise ManifestError(f"Missing truth or saved audit for {identifier}.")
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        result = Result.from_dict(json.loads(audit_path.read_text(encoding="utf-8")))
        metric = score(truth, result)
        metric.update(
            {
                "id": identifier,
                "category": case.get("category", "unspecified"),
                "language": case.get("language", "unspecified"),
                "source_sha256": case["sha256"],
            }
        )
        metrics.append(metric)
    (output / "results.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_results(metrics, output / "RESULTS.md", run.get("suite", manifest_path.stem))
    return metrics


def write_results(metrics: list[dict[str, Any]], path: Path, suite: str) -> None:
    lines = [
        f"# Blind evaluation: {suite}",
        "",
        "Truth was unavailable to the extractor. Saved, source-bound audits were scored later without rerunning extraction.",
        "",
        "| Case | Category | Language | Cells exact | Rows | Headers | Shape | Result |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for metric in metrics:
        lines.append(
            f"| {metric['id']} | {metric['category']} | {metric['language']} | "
            f"{metric['cell_exact']:.1%} | {metric['row_match']:.1%} | "
            f"{metric['header_match']:.1%} | {metric['shape_match']} | "
            f"{'PASS' if metric['pass'] else 'FAIL'} |"
        )
    lines += [
        "",
        f"Exact passes: **{sum(item['pass'] for item in metrics)}/{len(metrics)}**.",
        "",
        "A pass requires exact cells, headers, table shapes and all annotated injected errors. Results apply only to this frozen suite.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
