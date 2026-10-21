"""Content-led validation using Decimal arithmetic and explicit evidence thresholds."""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal
from itertools import combinations, permutations

from .models import Issue, Table
from .semantics import ColumnSemantic, infer_column_semantics, value_matches
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
        counts = Counter(
            kind(row[c])
            for row in table.rows
            if c < len(row) and row[c].strip() and not total_row(row)
        )
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
    semantics = infer_column_semantics(table)

    def add(
        r: int | None,
        c: int | None,
        code: str,
        reason: str,
        severity: str = "warning",
        suggestion: str = "Compare with the source document.",
        page_override: int | None = None,
    ) -> None:
        sources = table.provenance[r] if r is not None else [(table.page, None)]
        page, source_row = sources[0]
        if page_override is not None:
            page = page_override
        issues.append(
            Issue(
                severity,
                page,
                source_row,
                c + 1 if c is not None else None,
                reason,
                suggestion,
                code,
                table_index,
            )
        )

    title_records = []
    seen_titles = set()
    for record in table.page_summaries:
        if record.get("role") != "document_title":
            continue
        key = (
            int(record.get("page", table.page)),
            str(record.get("text", "")),
            tuple(record.get("bbox") or ()),
        )
        if key not in seen_titles:
            title_records.append(record)
            seen_titles.add(key)
    for record in title_records:
        title = str(record.get("text", ""))
        issues.append(
            Issue(
                "warning",
                int(record.get("page", table.page)),
                None,
                None,
                f"Full-width document title {title!r} retained separately from column headers.",
                "Verify the source page and reconstructed headers.",
                "layout_review",
                table_index,
            )
        )
    for note in table.notes:
        if title_records and note.startswith("Full-width document title "):
            # Old checkpoints may contain the pre-attribution title note as
            # well as the page summary. The summary owns the precise page.
            continue
        for page in sorted({p for sources in table.provenance for p, _ in sources} or {table.page}):
            issues.append(
                Issue(
                    "warning",
                    page,
                    None,
                    None,
                    note,
                    "Verify the source page and reconstructed cells.",
                    "layout_review",
                    table_index,
                )
            )
    for c, sources in enumerate(table.header_sources):
        for source in sources:
            if source.get("role") == "header_recheck":
                issues.append(
                    Issue(
                        "warning",
                        source["page"],
                        None,
                        c + 1,
                        f"Header re-read: {source.get('initial_reading')!r} -> {source.get('text')!r}; English model agreed at two scales.",
                        "Verify the source header; model agreement is not certainty.",
                        "header_disagreement",
                        table_index,
                    )
                )
    for c, inferred in enumerate(types):
        if inferred == "empty":
            add(None, c, "empty_column", "Column is entirely empty.")
    seen: dict[tuple, int] = {}
    for r, row in enumerate(table.rows):
        if len(row) != len(table.headers):
            add(
                r,
                None,
                "column_count",
                f"Expected {len(table.headers)} columns; found {len(row)}.",
                "error",
            )
        if sum(bool(v.strip()) for v in row) < max(2, len(table.headers) * 0.4):
            add(
                r,
                None,
                "sparse_row",
                "Sparse row may contain a wrapped cell, merged region or missing values.",
            )
        signature = tuple(row)
        if signature in seen:
            add(
                r,
                None,
                "duplicate_row",
                "Identical business row retained; confirm whether it is a legitimate duplicate.",
            )
        seen[signature] = r
        if total_row(row):
            continue
        for c, value in enumerate(row[: len(types)]):
            if "\ufffd" in value:
                add(
                    r,
                    c,
                    "unmapped_glyph",
                    "The PDF text layer contains an unmapped character; inspect this source cell or run independent OCR.",
                )
            for reading in table.cell_sources[r][c]:
                if reading.get("role") == "comparison" and reading.get("text") != value:
                    add(
                        r,
                        c,
                        "ocr_disagreement",
                        f"Alternate {reading['engine']} ({reading.get('strategy', '')}) read {reading.get('text')!r}; selected {value!r}.",
                    )
            actual = kind(value)
            if actual == "currency":
                actual = "numeric"
            if value and types[c] in {"numeric", "date", "id"} and actual != types[c]:
                add(
                    r,
                    c,
                    "type_mismatch",
                    f"Column usually contains {types[c]}; this value is {actual}.",
                )
            if "ocr" in table.row_engines[r]:
                conf = table.cell_confidence.get((r, c), table.confidence)
                if conf < 0.85:
                    add(
                        r,
                        c,
                        "ocr_confidence",
                        f"OCR recognition confidence {conf:.2f}; verify all characters.",
                    )
                if types[c] == "numeric" and re.search(r"[OlISB]", value):
                    add(
                        r,
                        c,
                        "ocr_digit_risk",
                        "Possible OCR digit/letter confusion in numeric column.",
                    )
                if types[c] == "numeric" and value.count(".") > 1:
                    add(
                        r,
                        c,
                        "decimal_risk",
                        "Multiple decimal separators in a numeric column.",
                    )
    _check_totals(table, add)
    _discover_arithmetic(table, types, semantics, add)
    _running_balance(table, types, semantics, add)
    _check_semantic_cells(table, semantics, add)
    _check_shifted_rows(table, semantics, add)
    _check_sequences(table, semantics, add)
    _check_cross_page_continuity(table, semantics, add)
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
                    add(
                        r,
                        c,
                        "ambiguous_date",
                        "Ambiguous day/month order; preserved as text.",
                    )
        if len(formats) >= 3:
            common = Counter(fmt for _, fmt in formats).most_common(1)[0][0]
            for r, fmt in formats:
                if fmt != common:
                    add(
                        r,
                        c,
                        "date_format",
                        "Date layout differs from the column majority.",
                    )
    return issues


def _business_rows(table: Table) -> list[int]:
    return [r for r, row in enumerate(table.rows) if not total_row(row)]


def _check_semantic_cells(table: Table, semantics: list[ColumnSemantic], add) -> None:
    """Validate high-risk roles and infer requiredness only from recurring evidence."""
    rows = _business_rows(table)
    for c, semantic in enumerate(semantics):
        if semantic.role == "text" or semantic.confidence < 0.75:
            continue
        populated = [r for r in rows if c < len(table.rows[r]) and table.rows[r][c].strip()]
        if semantic.header_signal:
            for r in populated:
                value = table.rows[r][c]
                if value_matches(semantic.role, value) is False:
                    add(
                        r,
                        c,
                        "semantic_type_mismatch",
                        f"Value {value!r} does not match the inferred {semantic.role} role "
                        f"({semantic.evidence}).",
                    )
        # A column is treated as locally required only when the current document
        # itself provides a strong near-complete pattern. This is a review flag,
        # not a schema rule and never causes data insertion.
        if (
            semantic.header_signal
            and len(rows) >= 5
            and len(populated) >= 4
            and len(populated) / len(rows) >= 0.8
        ):
            for r in rows:
                if c >= len(table.rows[r]) or not table.rows[r][c].strip():
                    add(
                        r,
                        c,
                        "required_value_missing",
                        f"This {semantic.role} column is populated in "
                        f"{len(populated)}/{len(rows)} comparable rows; the blank requires review.",
                    )


def _check_shifted_rows(table: Table, semantics: list[ColumnSemantic], add) -> None:
    """Flag a likely one-column shift only when semantic fit improves materially."""
    reliable = [
        c
        for c, semantic in enumerate(semantics)
        if semantic.role != "text" and semantic.confidence >= 0.75
    ]
    if len(reliable) < 3:
        return
    for r in _business_rows(table):
        row = table.rows[r]

        def score(offset: int) -> int:
            matched = 0
            for target in reliable:
                source = target + offset
                if 0 <= source < len(row):
                    matched += value_matches(semantics[target].role, row[source]) is True
            return matched

        baseline = score(0)
        alternatives = [(score(-1), -1), (score(1), 1)]
        best, offset = max(alternatives)
        if best >= max(2, round(len(reliable) * 0.7)) and best >= baseline + 2:
            direction = "left" if offset == 1 else "right"
            add(
                r,
                None,
                "shifted_columns",
                f"Values fit neighbouring semantic columns better than their current columns; "
                f"a one-column shift to the {direction} is possible ({best} vs {baseline} matches).",
            )


def _sequence_candidates(table: Table, semantics: list[ColumnSemantic]) -> list[tuple[int, list]]:
    candidates = []
    for c, semantic in enumerate(semantics):
        if semantic.role != "id" or semantic.confidence < 0.84:
            continue
        values = []
        for r in _business_rows(table):
            if c >= len(table.rows[r]):
                continue
            text = table.rows[r][c].strip()
            if re.fullmatch(r"\d+", text):
                values.append((r, int(text), text))
        if len(values) < 5:
            continue
        deltas = [current[1] - previous[1] for previous, current in zip(values, values[1:])]
        if deltas and sum(delta == 1 for delta in deltas) / len(deltas) >= 0.7:
            candidates.append((c, values))
    return candidates


def _check_sequences(table: Table, semantics: list[ColumnSemantic], add) -> None:
    """Detect missing or repeated records in strongly sequential identifier columns."""
    for c, values in _sequence_candidates(table, semantics):
        for previous, current in zip(values, values[1:]):
            if current[1] == previous[1] + 1:
                continue
            previous_page = table.provenance[previous[0]][0][0]
            current_page = table.provenance[current[0]][0][0]
            if current_page != previous_page:
                continue
            expected = str(previous[1] + 1).zfill(len(previous[2]))
            add(
                current[0],
                c,
                "sequence_gap",
                f"Sequential identifier follows {previous[2]!r} with {current[2]!r}; "
                f"expected {expected!r}. A missing, duplicate or misread row is possible.",
            )


def _check_cross_page_continuity(table: Table, semantics: list[ColumnSemantic], add) -> None:
    """Check page boundaries, provenance receipts and explicit record-count statements."""
    for c, values in _sequence_candidates(table, semantics):
        for previous, current in zip(values, values[1:]):
            previous_page = table.provenance[previous[0]][0][0]
            current_page = table.provenance[current[0]][0][0]
            if current_page == previous_page or current[1] == previous[1] + 1:
                continue
            expected = str(previous[1] + 1).zfill(len(previous[2]))
            add(
                current[0],
                c,
                "cross_page_sequence_gap",
                f"Identifier continuity changes from {previous[2]!r} on page {previous_page} "
                f"to {current[2]!r} on page {current_page}; expected {expected!r}.",
                "error",
                "Inspect the end and start of both pages for a missing or split record.",
            )

    receipt = table.join_receipt
    pages = [int(page) for page in receipt.get("pages", [])]
    if pages and pages != list(range(min(pages), max(pages) + 1)):
        add(
            None,
            None,
            "page_continuity_gap",
            f"Joined table provenance skips pages: {pages}.",
            "error",
            "Confirm whether the missing page contains a continuation table.",
        )
    if pages and int(receipt.get("page_joins", 0)) != max(0, len(pages) - 1):
        add(
            None,
            None,
            "join_receipt_mismatch",
            f"Join receipt reports {receipt.get('page_joins', 0)} joins for {len(pages)} pages.",
            "error",
            "Regenerate the extraction and verify each page boundary.",
        )
    if receipt.get("rows_by_page"):
        observed = Counter(
            page for row_sources in table.provenance for page, _source_row in row_sources
        )
        recorded = {int(item["page"]): int(item["rows"]) for item in receipt["rows_by_page"]}
        if dict(observed) != recorded:
            add(
                None,
                None,
                "provenance_count_mismatch",
                f"Join receipt row counts {recorded} differ from retained provenance {dict(observed)}.",
                "error",
                "Regenerate the extraction; do not approve this join receipt.",
            )

    declared = []
    count_pattern = re.compile(
        r"(?:grand\s+)?total\s+(?:records?|rows?|entries|persons?)\s*[:=#-]?\s*(\d+)"
        r"|(\d+)\s+total\s+(?:records?|rows?|entries|persons?)\b",
        re.I,
    )
    for record in table.page_summaries:
        match = count_pattern.search(str(record.get("text", "")))
        if match:
            declared.append((record, int(next(group for group in match.groups() if group))))
    business_count = len(_business_rows(table))
    for record, expected in declared:
        if expected != business_count:
            issues_page = int(record.get("page", table.page))
            add(
                None,
                None,
                "record_count_mismatch",
                f"Source page {issues_page} declares {expected} records; "
                f"the reconstructed table contains {business_count} business rows.",
                "error",
                "Check for missing, duplicated or incorrectly joined rows.",
                issues_page,
            )


def _check_totals(table: Table, add) -> None:
    start = 0
    for r, row in enumerate(table.rows):
        if not total_row(row):
            continue
        is_grand = any(re.search(r"grand\s+total", cell, re.I) for cell in row)
        block = table.rows[0 if is_grand else start : r]
        for c, displayed in enumerate(row):
            actual = number(displayed)
            if actual is None:
                continue
            values = [
                record[c]
                for record in block
                if c < len(record) and not total_row(record) and record[c].strip()
            ]
            parsed = [number(v) for v in values]
            if not parsed or any(v is None for v in parsed):
                continue
            expected = sum(parsed, Decimal(0))
            if abs(actual - expected) > tolerance(values + [displayed]):
                add(
                    r,
                    c,
                    "total_mismatch",
                    f"Displayed total {actual} differs from column sum {expected}.",
                    "error",
                    f"Verify source; expected sum {expected}. Do not overwrite automatically.",
                )
        start = r + 1


def _discover_arithmetic(
    table: Table, types: list[str], semantics: list[ColumnSemantic], add
) -> None:
    numeric = [
        c
        for c, value_type in enumerate(types)
        if value_type == "numeric" and semantics[c].role not in {"id", "phone", "date"}
    ][:14]
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
                if sum(o[1] for o in observations) / len(observations) >= 0.8:
                    for r, matches, expected, _ in observations:
                        if not matches:
                            add(
                                r,
                                target,
                                "row_arithmetic",
                                f"Inferred C{a + 1} {operator} C{b + 1} = C{target + 1}; expected {expected}.",
                                "error",
                            )


def _running_balance(table: Table, types: list[str], semantics: list[ColumnSemantic], add) -> None:
    numeric = [
        c
        for c, value_type in enumerate(types)
        if value_type == "numeric" and semantics[c].role not in {"id", "phone", "date"}
    ][:12]
    candidates = []
    named_balances = [c for c in numeric if semantics[c].role == "balance"]
    for balance in named_balances or numeric:
        others = [c for c in numeric if c != balance]
        for debit, credit in permutations(others, 2):
            evidence = []
            for r in range(1, len(table.rows)):
                previous, row = table.rows[r - 1], table.rows[r]
                if (
                    total_row(previous)
                    or total_row(row)
                    or max(balance, debit, credit) >= min(len(row), len(previous))
                ):
                    continue
                values = [
                    number(previous[balance]),
                    number(row[balance]),
                    number(row[debit]),
                    number(row[credit]),
                ]
                if any(v is None for v in values):
                    continue
                before, after, outflow, inflow = values
                expected = before - outflow + inflow
                evidence.append(
                    (
                        r,
                        abs(after - expected) <= Decimal("0.01"),
                        expected,
                        before != after,
                    )
                )
            if len(evidence) >= 6 and sum(v[3] for v in evidence) >= 4:
                ratio = sum(v[1] for v in evidence) / len(evidence)
                if ratio >= 0.7:
                    candidates.append((ratio, balance, debit, credit, evidence))
    # Only the strongest content-supported relation is used.
    if candidates:
        _, balance, debit, credit, evidence = max(candidates, key=lambda c: c[0])
        for r, match, expected, _ in evidence:
            if not match:
                add(
                    r,
                    balance,
                    "running_balance",
                    f"Inferred C{balance + 1}[previous] - C{debit + 1} + C{credit + 1}; expected {expected}.",
                    "error",
                )
