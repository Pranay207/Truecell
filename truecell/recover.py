"""Candidate evaluation that penalizes missing content as well as validation failures."""

from __future__ import annotations

from .models import Table
from .validate import validate
from .values import kind


def candidate_key(candidate: tuple) -> tuple:
    """Rank direct native grid evidence ahead of unrelated page-text coverage."""
    score, tables, _ = candidate
    trusted = bool(tables) and all(
        t.engine == "native-lines"
        and all(len(row) == len(t.headers) for row in t.rows)
        and (
            t.header_detected
            or len(t.rows) >= 3
            and any(kind(v) in {"numeric", "currency", "date", "id"} for row in t.rows for v in row)
        )
        for t in tables
    )
    if not tables:
        return False, False, -1, score
    if all(t.engine == "native-anchors" for t in tables):
        trusted = True
    cells = sum(len(row) for t in tables for row in t.rows)
    filled = sum(sum(bool(v) for v in row) for t in tables for row in t.rows)
    named = sum(sum(not h.startswith("Column ") for h in t.headers) for t in tables)
    headers = sum(len(t.headers) for t in tables)
    alignment = all(any("repeated word positions" in note for note in t.notes) for t in tables)
    quality = (
        0.5 * filled / max(1, cells)
        + 0.2 * named / max(1, headers)
        + 0.3 * all(t.header_detected for t in tables)
    )
    if alignment:
        quality += 0.3
    if any(t.engine.startswith("ocr-") for t in tables):
        # Upside-down digits often become letters and masquerade as a header.
        # Dense nonsense must not outrank an upright table with sparse totals.
        label_strength = sum(
            sum(ch.isalpha() for ch in header) / max(1, sum(ch.isalnum() for ch in header))
            for t in tables
            for header in t.headers
        ) / max(1, headers)
        quality -= 0.3 * (1 - label_strength)
        structural = sum(
            issue.code in {"type_mismatch", "ocr_confidence", "ocr_digit_risk", "column_count"}
            for t in tables
            for issue in validate(t)
        )
        quality -= min(0.4, structural / max(1, cells))
    # A structurally dense rotated OCR hallucination can look superficially
    # complete while validation-adjusted content evidence is net negative.
    # Keep layout quality ahead of score only among credible candidates.
    credible = trusted or score >= 0
    return trusted, credible, round(quality, 1), score


def evaluate(tables: list[Table]) -> tuple[float, int, int]:
    """Return score, findings and nonempty cells; empty extraction never wins."""
    if not tables:
        return -10000, 0, 0
    cells = sum(sum(bool(v) for v in row) for t in tables for row in t.rows)
    issues = [issue for t in tables for issue in validate(t)]
    # A source's wrong total is not an extraction defect. Penalizing it can
    # reward losing the total row or replacing a good grid with page prose.
    structural_codes = {
        "column_count",
        "type_mismatch",
        "ocr_confidence",
        "ocr_digit_risk",
        "decimal_risk",
    }
    errors = sum(i.severity == "error" and i.code in structural_codes for i in issues)
    risks = sum(
        i.code in {"type_mismatch", "ocr_confidence", "ocr_digit_risk", "decimal_risk"}
        for i in issues
    )
    # A word split into three false columns must not earn triple coverage.
    # Whitespace-free character coverage is stable under alternate segmentation.
    characters = sum(len("".join(value.split())) for t in tables for row in t.rows for value in row)
    width_penalty = sum(len(t.headers) * 3 for t in tables)
    generic_penalty = sum(sum(h.startswith("Column ") for h in t.headers) * 12 for t in tables)
    structural_count = sum(i.code in structural_codes or i.code == "sparse_row" for i in issues)
    rows = sum(len(t.rows) for t in tables)
    sparse = sum(sum(bool(v) for v in row) < len(t.headers) * 0.4 for t in tables for row in t.rows)
    score = (
        characters - width_penalty - generic_penalty - errors * 8 - structural_count * 2 - risks * 5
    )
    score -= 180 * sparse / max(1, rows)
    if all(t.engine == "native-lines" for t in tables):
        # Explicit ruling is direct layout evidence, unlike a larger free-text
        # candidate. Keep faithful source errors and let validation expose them.
        score += 1000
    score += sum(t.confidence for t in tables) * 20
    return round(score, 3), len(issues), cells


def needs_retry(tables: list[Table]) -> bool:
    """Retry substantive uncertainty, not the universal OCR source-review notice."""
    if not tables:
        return True
    return any(
        t.confidence < 0.85
        or not t.header_detected
        or any(h.startswith("Column ") for h in t.headers)
        or any(
            i.code
            in {
                "column_count",
                "ocr_confidence",
                "ocr_digit_risk",
                "type_mismatch",
                "decimal_risk",
            }
            for i in validate(t)
        )
        for t in tables
    )
