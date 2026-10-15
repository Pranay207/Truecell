"""Candidate evaluation that penalizes missing content as well as validation failures."""
from __future__ import annotations

from .models import Table
from .validate import validate


def evaluate(tables: list[Table]) -> tuple[float, int, int]:
    """Return score, findings and nonempty cells; empty extraction never wins."""
    if not tables:
        return -10000, 0, 0
    cells = sum(sum(bool(v) for v in row) for t in tables for row in t.rows)
    issues = [issue for t in tables for issue in validate(t)]
    errors = sum(i.severity == "error" for i in issues)
    risks = sum(i.code in {"type_mismatch", "ocr_confidence", "ocr_digit_risk", "decimal_risk"} for i in issues)
    # A word split into three false columns must not earn triple coverage.
    # Whitespace-free character coverage is stable under alternate segmentation.
    characters = sum(len("".join(value.split())) for t in tables for row in t.rows for value in row)
    width_penalty = sum(len(t.headers) * 3 for t in tables)
    generic_penalty = sum(sum(h.startswith("Column ") for h in t.headers) * 12 for t in tables)
    score = characters - width_penalty - generic_penalty - errors * 8 - len(issues) * 2 - risks * 5
    score += sum(t.confidence for t in tables) * 20
    return round(score, 3), len(issues), cells


def needs_retry(tables: list[Table]) -> bool:
    """Retry substantive uncertainty, not the universal OCR source-review notice."""
    if not tables:
        return True
    return any(t.confidence < .85 or any(
        i.severity == "error" or i.code in {"ocr_confidence", "ocr_digit_risk", "type_mismatch", "decimal_risk"}
        for i in validate(t)) for t in tables)
