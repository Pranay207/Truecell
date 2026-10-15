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
    # Content coverage dominates small differences in heuristic validation counts.
    score = cells - errors * 8 - len(issues) * .5
    score += sum(t.confidence for t in tables) * 5
    return round(score, 3), len(issues), cells
