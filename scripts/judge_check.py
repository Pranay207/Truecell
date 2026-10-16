"""One command to reproduce sample conversion and strict PASS/FAIL evaluation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.score import run, write_report

if __name__ == "__main__":
    metrics = run(ROOT / "samples", ROOT / "outputs")
    write_report(metrics, ROOT / "reports" / "ACCURACY_REPORT.md")
    passed = sum(m["pass"] for m in metrics)
    print(
        f"\n{passed}/{len(metrics)} exact cases passed. See reports/ACCURACY_REPORT.md for failures."
    )
    raise SystemExit(0 if metrics and passed == len(metrics) else 1)
