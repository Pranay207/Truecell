"""Join adjacent compatible tables without dropping duplicate business records."""

from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from difflib import SequenceMatcher

from .models import Issue, Table
from .semantics import normalized_header, semantic_roles
from .table import clean


def _receipt(table: Table) -> dict:
    """Return a stable, JSON-safe account of how page fragments became a table."""
    receipt = table.join_receipt
    receipt.setdefault("page_joins", 0)
    receipt.setdefault("repeated_headers_removed", 0)
    receipt.setdefault("split_rows_recovered", 0)
    table.join_receipt = receipt
    return receipt


def _refresh_receipt(table: Table) -> None:
    """Derive page and row totals from final provenance after all joins."""
    receipt = _receipt(table)
    rows_by_page = Counter(page for sources in table.provenance for page, _source_row in sources)
    pages = sorted(rows_by_page or {table.page: 0})
    receipt.update(
        {
            "pages": pages,
            "rows_by_page": [{"page": page, "rows": rows_by_page[page]} for page in pages],
            "output_rows": len(table.rows),
        }
    )


def _summary_key(record: dict) -> tuple:
    bbox = record.get("bbox")
    return (
        int(record.get("page", 0)),
        str(record.get("role", "")),
        clean(record.get("text", "")),
        tuple(bbox) if bbox else (),
    )


def _merge_page_summaries(target: Table, source: Table) -> None:
    """Merge page evidence once while retaining the page that produced it."""
    seen = {_summary_key(record) for record in target.page_summaries}
    for record in source.page_summaries:
        key = _summary_key(record)
        if key not in seen:
            target.page_summaries.append(record)
            seen.add(key)


def _generic_header(value: str) -> bool:
    return bool(re.fullmatch(r"column\s+\d+", clean(value), re.I))


def _weak_header(value: str) -> bool:
    """Identify declared placeholders and visibly damaged short fragments."""
    text = clean(value)
    return (
        not text
        or _generic_header(text)
        or text.count("(") != text.count(")")
        or text.count("[") != text.count("]")
        or len("".join(c for c in text if c.isalpha())) <= 2
    )


def _header_similarity(left: Table, right: Table) -> float:
    pairs = zip(left.headers, right.headers)
    return sum(
        SequenceMatcher(None, normalized_header(a), normalized_header(b)).ratio() > 0.78
        for a, b in pairs
    ) / max(1, len(left.headers))


def _semantic_similarity(left: Table, right: Table) -> float:
    a, b = semantic_roles(left), semantic_roles(right)
    return sum(x == y for x, y in zip(a, b)) / max(1, len(a))


def _header_votes(table: Table) -> list[dict[str, dict]]:
    votes = getattr(table, "_truecell_header_votes", None)
    if votes is None:
        votes = []
        for column, value in enumerate(table.headers):
            pages = {
                int(source.get("page", table.page)) for source in table.header_sources[column]
            } or {table.page}
            votes.append(
                {
                    normalized_header(value): {
                        "value": value,
                        "count": 1,
                        "pages": pages,
                        "sources": list(table.header_sources[column]),
                    }
                }
            )
        setattr(table, "_truecell_header_votes", votes)
    return votes


def _record_header_readings(target: Table, source: Table) -> list[tuple[int, str, str, set[int]]]:
    """Accumulate page readings and return evidence-supported header repairs."""
    votes = _header_votes(target)
    repairs = []
    for column, value in enumerate(source.headers):
        key = normalized_header(value)
        pages = {
            int(record.get("page", source.page)) for record in source.header_sources[column]
        } or {source.page}
        record = votes[column].setdefault(
            key,
            {"value": value, "count": 0, "pages": set(), "sources": []},
        )
        record["count"] += 1
        record["pages"].update(pages)
        record["sources"].extend(source.header_sources[column])
        current_key = normalized_header(target.headers[column])
        winner_key, winner = max(
            votes[column].items(),
            key=lambda item: (item[1]["count"], not _weak_header(item[1]["value"])),
        )
        current = votes[column].get(current_key, {"count": 0})
        supported_consensus = winner["count"] >= 2 and winner["count"] > current["count"]
        placeholder_repair = _weak_header(target.headers[column]) and not _weak_header(value)
        if winner_key != current_key and (supported_consensus or placeholder_repair):
            old = target.headers[column]
            selected = winner["value"] if supported_consensus else value
            selected_pages = winner["pages"] if supported_consensus else pages
            target.headers[column] = selected
            target.header_sources[column].append(
                {
                    "page": min(selected_pages),
                    "bbox": None,
                    "text": selected,
                    "engine": "stitch-header-consensus",
                    "confidence": None,
                    "coordinates": "page points",
                    "role": "header_consensus_repair",
                    "initial_reading": old,
                    "supporting_pages": sorted(selected_pages),
                }
            )
            repairs.append((column, old, selected, set(selected_pages)))
    return repairs


def compatible(left: Table, right: Table) -> bool:
    """Require adjacent pages, matching shape, x-span and compatible headers."""
    last_page = (
        max(p for sources in left.provenance for p, _ in sources) if left.rows else left.page
    )
    if right.page != last_page + 1 or len(left.headers) != len(right.headers):
        return False
    width = max(1, left.bbox[2] - left.bbox[0])
    if max(abs(left.bbox[i] - right.bbox[i]) for i in (0, 2)) / width > 0.08:
        return False
    if not right.header_detected:
        return True
    similarity = _header_similarity(left, right)
    if similarity >= 0.65:
        return True
    weak = sum(_weak_header(value) for value in left.headers + right.headers)
    return weak > 0 and similarity >= 0.4 and _semantic_similarity(left, right) >= 0.75


def stitch(tables: list[Table]) -> tuple[list[Table], list[Issue]]:
    """Keep source row provenance and flag inferred joins for human review."""
    joined: list[Table] = []
    issues: list[Issue] = []
    for source in tables:
        table = deepcopy(source)
        _receipt(table)
        matches = [t for t in joined if compatible(t, table)]
        if len(matches) != 1:
            joined.append(table)
            continue
        target = matches[0]
        header_repairs = _record_header_readings(target, table) if table.header_detected else []
        if table.header_detected:
            repaired_columns = {repair[0] for repair in header_repairs}
            disagreements = [
                c
                for c, (left, right) in enumerate(zip(target.headers, table.headers))
                if c not in repaired_columns
                and SequenceMatcher(None, normalized_header(left), normalized_header(right)).ratio()
                <= 0.78
            ]
            for column in disagreements:
                issues.append(
                    Issue(
                        "warning",
                        table.page,
                        None,
                        column + 1,
                        f"Continuation header {table.headers[column]!r} differs from the retained "
                        f"reading {target.headers[column]!r}; values were preserved.",
                        "Compare the page headers before approving the joined table.",
                        "page_header_disagreement",
                        joined.index(target) + 1,
                    )
                )
        for column, old, selected, pages in header_repairs:
            issues.append(
                Issue(
                    "warning",
                    table.page,
                    None,
                    column + 1,
                    f"Header repaired from {old!r} to {selected!r} using page-header evidence "
                    f"from pages {sorted(pages)}.",
                    "Verify the selected header against the cited source pages.",
                    "header_consensus_repair",
                    joined.index(target) + 1,
                )
            )
            target.join_receipt["header_repairs"] = target.join_receipt.get("header_repairs", 0) + 1
        target_receipt = _receipt(target)
        source_receipt = _receipt(table)
        target_receipt["page_joins"] += source_receipt["page_joins"] + 1
        target_receipt["repeated_headers_removed"] += source_receipt[
            "repeated_headers_removed"
        ] + int(table.header_detected)
        target_receipt["split_rows_recovered"] += source_receipt["split_rows_recovered"]
        if not table.header_detected:
            issues.append(
                Issue(
                    "warning",
                    table.page,
                    1,
                    None,
                    "Headerless continuation joined by column count and horizontal span.",
                    code="inferred_join",
                    table=joined.index(target) + 1,
                )
            )
        offset = len(target.rows)
        # Join complementary page-break fragments only with strong structural evidence.
        if (
            target.rows
            and table.rows
            and len(target.rows[-1]) == len(table.headers)
            and len(table.rows[0]) == len(table.headers)
        ):
            before, after = target.rows[-1], table.rows[0]
            tail_holes = [c for c in range(1, len(before)) if not before[c]]
            filled = [c for c in tail_holes if after[c]]
            overlaps = [c for c in range(1, len(before)) if before[c] and after[c]]
            from .values import kind

            if (
                before[0]
                and not after[0]
                and len(filled) >= 2
                and overlaps
                and all(kind(before[c]) == kind(after[c]) == "text" for c in overlaps)
            ):
                for c in range(len(before)):
                    scores = []
                    if before[c]:
                        scores.append(
                            target.cell_confidence.get((offset - 1, c), target.confidence)
                        )
                    if after[c]:
                        scores.append(table.cell_confidence.get((0, c), table.confidence))
                    if scores:
                        target.cell_confidence[offset - 1, c] = min(scores)
                    if clean(before[c]).casefold() == clean(after[c]).casefold():
                        before[c] = clean(before[c])
                    else:
                        before[c] = clean(before[c] + " " + after[c])
                target.provenance[-1].extend(table.provenance[0])
                target.row_engines[-1] += "+" + table.row_engines[0]
                for c in range(len(before)):
                    target.cell_sources[-1][c].extend(table.cell_sources[0][c])
                issues.append(
                    Issue(
                        "warning",
                        table.page,
                        table.provenance[0][0][1],
                        None,
                        "Complementary page-break row fragments merged; verify the reconstructed record.",
                        code="split_row_join",
                        table=joined.index(target) + 1,
                    )
                )
                target_receipt["split_rows_recovered"] += 1
                table.rows.pop(0)
                table.provenance.pop(0)
                table.row_engines.pop(0)
                table.cell_sources.pop(0)
                table.cell_confidence = {
                    (r - 1, c): v for (r, c), v in table.cell_confidence.items() if r > 0
                }
        target.rows.extend(table.rows)
        _merge_page_summaries(target, table)
        target.provenance.extend(table.provenance)
        target.row_engines.extend(table.row_engines)
        target.cell_sources.extend(table.cell_sources)
        if table.header_detected:
            for c in range(len(target.headers)):
                target.header_sources[c].extend(table.header_sources[c])
        if table.engine not in target.engine.split("+"):
            target.engine += "+" + table.engine
        for (r, c), confidence in table.cell_confidence.items():
            target.cell_confidence[(r + offset, c)] = confidence
        target.notes.extend(note for note in table.notes if note not in target.notes)
        target.confidence = min(target.confidence, table.confidence)
    for table in joined:
        _refresh_receipt(table)
        if hasattr(table, "_truecell_header_votes"):
            delattr(table, "_truecell_header_votes")
    return joined, issues
