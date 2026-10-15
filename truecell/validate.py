"""Content-led validation using Decimal arithmetic and explicit evidence thresholds."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from itertools import combinations, permutations
import re

from .models import Issue, Table
from .values import kind, number

TOTAL = re.compile(r"\b(?:total|subtotal|grand\s+total|sum|net\s+total|amt\s+total)\b", re.I)


def total_row(row: list[str]) -> bool:
    """Match total keywords in any cell, avoiding ordinary transaction balances."""
    return any(TOTAL.search(c) for c in row)


def tolerance(values: list[str]) -> Decimal:
    """Half a unit of the least precise displayed decimal place."""
    places = [len(v.rsplit(".", 1)[1]) if "." in v else 0 for v in values]
    return Decimal(5).scaleb(-min(places, default=0) - 1)


def classify_columns(table: Table) -> list[str]:
    """Infer dominant content type from nonempty, non-total rows."""
    kinds = []
    for c in range(len(table.headers)):
        counts = Counter(kind(row[c]) for row in table.rows
                         if c < len(row) and row[c].strip() and not total_row(row))
        # Currency and plain numeric cells share the same structural expectation.
        currency_count = counts.pop("currency", 0)
        if currency_count:
            counts["numeric"] += currency_count
        kinds.append(counts.most_common(1)[0][0] if counts else "empty")
    return kinds


def validate(table: Table, table_index: int = 1) -> list[Issue]:
    """Find structural, arithmetic and OCR risks without changing extracted values."""
    issues: list[Issue] = []
    types = classify_columns(table)

    def add(r: int | None, c: int | None, code: str, reason: str,
            severity: str = "warning", suggestion: str = "Compare with the source document.") -> None:
        sources = table.provenance[r] if r is not None else [(table.page, None)]
        page, source_row = sources[0]
        issues.append(Issue(severity, page, source_row, c + 1 if c is not None else None,
                            reason, suggestion, code, table_index))

    for note in table.notes:
        for page in sorted({p for sources in table.provenance for p, _ in sources} or {table.page}):
            issues.append(Issue("warning", page, None, None, note,
                                "Verify the source page and reconstructed cells.", "layout_review", table_index))
    for c, inferred in enumerate(types):
        if inferred == "empty":
            add(None, c, "empty_column", "Column is entirely empty.")
    seen: dict[tuple, int] = {}
    for r, row in enumerate(table.rows):
        if len(row) != len(table.headers):
            add(r, None, "column_count", f"Expected {len(table.headers)} columns; found {len(row)}.", "error")
        if sum(bool(v.strip()) for v in row) < max(2, len(table.headers) * .4):
            add(r, None, "sparse_row", "Sparse row may contain a wrapped cell, merged region or missing values.")
        signature = tuple(row)
        if signature in seen:
            add(r, None, "duplicate_row", "Identical business row retained; confirm whether it is a legitimate duplicate.")
        seen[signature] = r
        if total_row(row):
            continue
        for c, value in enumerate(row[:len(types)]):
            actual = kind(value)
            if actual == "currency":
                actual = "numeric"
            if value and types[c] in {"numeric", "date", "id"} and actual != types[c]:
                add(r, c, "type_mismatch", f"Column usually contains {types[c]}; this value is {actual}.")
            if "ocr" in table.row_engines[r]:
                conf = table.cell_confidence.get((r, c), table.confidence)
                if conf < .85:
                    add(r, c, "ocr_confidence", f"OCR recognition confidence {conf:.2f}; verify all characters.")
                if types[c] == "numeric" and re.search(r"[OlISB]", value):
                    add(r, c, "ocr_digit_risk", "Possible OCR digit/letter confusion in numeric column.")
                if types[c] == "numeric" and value.count(".") > 1:
                    add(r, c, "decimal_risk", "Multiple decimal separators in a numeric column.")
    _check_totals(table, add)
    _discover_arithmetic(table, types, add)
    _running_balance(table, types, add)
    for c in range(len(table.headers)):
        formats = []
        for r, row in enumerate(table.rows):
            if c >= len(row):
                continue
            value = row[c]
            match = re.fullmatch(r"(\d{1,4})([-/.])(\d{1,2})\2(\d{2,4})", value)
            if match:
                formats.append((r, (len(match[1]), match[2], len(match[4]))))
                if len(match[1]) <= 2 and int(match[1]) <= 12 and int(match[3]) <= 12:
                    add(r, c, "ambiguous_date", "Ambiguous day/month order; preserved as text.")
        if len(formats) >= 3:
            common = Counter(fmt for _, fmt in formats).most_common(1)[0][0]
            for r, fmt in formats:
                if fmt != common:
                    add(r, c, "date_format", "Date layout differs from the column majority.")
    return issues


def _check_totals(table: Table, add) -> None:
    start = 0
    for r, row in enumerate(table.rows):
        if not total_row(row):
            continue
        is_grand = any(re.search(r"grand\s+total", cell, re.I) for cell in row)
        block = table.rows[0 if is_grand else start:r]
        for c, displayed in enumerate(row):
            actual = number(displayed)
            if actual is None:
                continue
            values = [record[c] for record in block if c < len(record) and not total_row(record) and record[c].strip()]
            parsed = [number(v) for v in values]
            if not parsed or any(v is None for v in parsed):
                continue
            expected = sum(parsed, Decimal(0))
            if abs(actual - expected) > tolerance(values + [displayed]):
                add(r, c, "total_mismatch", f"Displayed total {actual} differs from column sum {expected}.",
                    "error", f"Verify source; expected sum {expected}. Do not overwrite automatically.")
        start = r + 1


def _discover_arithmetic(table: Table, types: list[str], add) -> None:
    numeric = [c for c, t in enumerate(types) if t == "numeric"][:14]
    rows = [(r, row) for r, row in enumerate(table.rows) if not total_row(row)]
    # Require at least five diverse examples and >=80% agreement, excluding all-zero identities.
    for a, b in combinations(numeric, 2):
        for target in numeric:
            if target in (a, b):
                continue
            for operator in ("*", "+"):
                observations = []
                for r, row in rows:
                    if max(a, b, target) >= len(row):
                        continue
                    x, y, z = (number(row[i]) for i in (a, b, target))
                    if None in (x, y, z) or x == 0 or y == 0:
                        continue
                    expected = x * y if operator == "*" else x + y
                    observations.append((r, abs(z - expected) <= Decimal("0.01"), expected, (x, y)))
                if len(observations) < 5 or len({o[3] for o in observations}) < 4:
                    continue
                if sum(o[1] for o in observations) / len(observations) >= .8:
                    for r, matches, expected, _ in observations:
                        if not matches:
                            add(r, target, "row_arithmetic", f"Inferred C{a+1} {operator} C{b+1} = C{target+1}; expected {expected}.", "error")


def _running_balance(table: Table, types: list[str], add) -> None:
    numeric = [c for c, t in enumerate(types) if t == "numeric"][:12]
    candidates = []
    for balance in numeric:
        others = [c for c in numeric if c != balance]
        for debit, credit in permutations(others, 2):
            evidence = []
            for r in range(1, len(table.rows)):
                previous, row = table.rows[r - 1], table.rows[r]
                if total_row(previous) or total_row(row) or max(balance, debit, credit) >= min(len(row), len(previous)):
                    continue
                values = [number(previous[balance]), number(row[balance]), number(row[debit]), number(row[credit])]
                if any(v is None for v in values):
                    continue
                before, after, outflow, inflow = values
                expected = before - outflow + inflow
                evidence.append((r, abs(after - expected) <= Decimal("0.01"), expected, before != after))
            if len(evidence) >= 6 and sum(v[3] for v in evidence) >= 4:
                ratio = sum(v[1] for v in evidence) / len(evidence)
                if ratio >= .7:
                    candidates.append((ratio, balance, debit, credit, evidence))
    # Only the strongest content-supported relation is used.
    if candidates:
        _, balance, debit, credit, evidence = max(candidates, key=lambda c: c[0])
        for r, match, expected, _ in evidence:
            if not match:
                add(r, balance, "running_balance", f"Inferred C{balance+1}[previous] - C{debit+1} + C{credit+1}; expected {expected}.", "error")
