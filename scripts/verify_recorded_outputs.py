"""Fast integrity check for committed PDF, truth, audit, and workbook evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.benchmark import ManifestError, _verify_workbook_matches_audit
from eval.score import score, write_report
from truecell.models import Result


def main() -> int:
    metrics = []
    for truth_path in sorted((ROOT / "samples").glob("*.truth.json")):
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        name = truth["name"]
        source = ROOT / "samples" / f"{name}.pdf"
        audit_path = ROOT / "outputs" / f"{name}.audit.json"
        workbook = ROOT / "outputs" / f"{name}.xlsx"
        if not source.is_file() or not audit_path.is_file() or not workbook.is_file():
            raise SystemExit(f"Missing committed evidence for {name}.")
        result = Result.from_dict(json.loads(audit_path.read_text(encoding="utf-8")))
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if result.source_sha256 != source_hash:
            raise SystemExit(f"Source hash mismatch for {name}.")
        try:
            _verify_workbook_matches_audit(workbook, result, name)
        except ManifestError as exc:
            raise SystemExit(f"Workbook mismatch for {name}: {exc}") from exc
        metric = score(truth, result)
        metrics.append(metric)
        print(
            f"{'PASS' if metric['pass'] else 'FAIL'} {name}: "
            f"exact={metric['cell_exact']:.2%}, shape={metric['shape_match']}",
            flush=True,
        )
    write_report(metrics, ROOT / "reports" / "ACCURACY_REPORT.md")
    passed = sum(metric["pass"] for metric in metrics)
    print(f"\n{passed}/{len(metrics)} recorded exact cases passed with bound source hashes.")
    return 0 if metrics and passed == len(metrics) else 1


if __name__ == "__main__":
    raise SystemExit(main())
