"""Exercise the bundled OCR route even on a host with Tesseract installed."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.score import score
from truecell import ocr
from truecell.pipeline import convert


def main() -> int:
    # Explicit test isolation: no optional system OCR can rescue these cases.
    ocr.available_engines = lambda: ["rapidocr"]
    destination = ROOT / "tmp/portable-ocr"
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for name in ["C_scanned_inventory", "D_blur_noise", "D_skew_5deg", "D_phone_photo"]:
        truth = json.loads((ROOT / "samples" / f"{name}.truth.json").read_text())
        result = convert(ROOT / "samples" / f"{name}.pdf", destination / f"{name}.xlsx")
        metric = score(truth, result)
        metric["selected_engines"] = sorted({t.engine for t in result.tables})
        assert all(a.engine != "tesseract" for p in result.pages for a in p.attempts)
        records.append(metric)
        print(f"{name}: {metric['cell_exact']:.2%}, pass={metric['pass']}", flush=True)
    report = {
        "scope": "Four synthetic development cases; Tesseract excluded by engine selection override. Not hidden-test accuracy or a cross-platform execution test.",
        "python": platform.python_version(),
        "host": platform.platform(),
        "cases": records,
    }
    (ROOT / "reports/PORTABLE_OCR.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if all(r["pass"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
