"""Review-only edits, reproducible fingerprints and an append-only change receipt."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone

from .constraints import analyze
from .models import Result
from .validate import validate

LOW_CONFIDENCE_THRESHOLD = 0.93
LOW_CONFIDENCE_LIMIT = 100


def digest(value: object) -> str:
    """Canonical content hash; this is change detection, not reviewer identity."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def fingerprint(result: Result) -> str:
    """Bind review to source, values, evidence, findings and edit history."""
    data = result.to_dict()
    data.pop("review", None)
    data.pop("seconds", None)
    return digest(data)


def history_valid(result: Result) -> bool:
    """Detect accidental edits to existing history or a broken event chain."""
    previous = result.source_sha256 or "initial"
    for event in result.history:
        record = {k: v for k, v in event.items() if k != "sha256"}
        if record.get("previous") != previous or digest(record) != event.get("sha256"):
            return False
        previous = event["sha256"]
    return True


def review_current(result: Result) -> bool:
    """Only an unchanged, explicitly reviewed snapshot can be labelled reviewed."""
    return (
        result.review.get("status") == "reviewed"
        and history_valid(result)
        and result.review.get("fingerprint") == fingerprint(result)
    )


def _issue_cell(result: Result, issue) -> tuple[int, int, int] | None:
    """Resolve a finding's source coordinates to a displayed table cell."""
    if issue.row is None:
        return None
    candidates = [issue.table - 1] if issue.table is not None else list(range(len(result.tables)))
    for table_index in candidates:
        if not 0 <= table_index < len(result.tables):
            continue
        table = result.tables[table_index]
        for row_index, sources in enumerate(table.provenance):
            if any(
                page == issue.page and (issue.row is None or source_row == issue.row)
                for page, source_row in sources
            ):
                width = len(table.rows[row_index])
                if not width:
                    return None
                column = max(0, min((issue.column or 1) - 1, width - 1))
                return table_index, row_index, column
    return None


def review_queue(result: Result) -> dict:
    """Build a bounded, source-addressable queue of findings and uncertain cells."""
    saved = result.review.get("item_reviews", {})
    if not isinstance(saved, dict):
        saved = {}
    items: list[dict] = []
    finding_ids: set[str] = set()
    finding_cells: set[tuple[int, int, int]] = set()

    for issue in result.issues:
        cell = _issue_cell(result, issue)
        if cell is not None:
            finding_cells.add(cell)
        identity = {
            "kind": "finding",
            "severity": issue.severity,
            "page": issue.page,
            "row": issue.row,
            "column": issue.column,
            "code": issue.code,
            "table": issue.table,
            "reason": issue.reason,
        }
        item_id = f"finding-{digest(identity)[:16]}"
        if item_id in finding_ids:
            continue
        finding_ids.add(item_id)
        item = {
            "id": item_id,
            "kind": "finding",
            "severity": issue.severity,
            "page": issue.page,
            "title": issue.code.replace("_", " ").strip().title() or "Validation finding",
            "reason": issue.reason,
            "suggestion": issue.suggestion,
            "table": (
                cell[0]
                if cell
                else issue.table - 1
                if issue.table is not None and 0 < issue.table <= len(result.tables)
                else None
            ),
            "row": cell[1] if cell else None,
            "column": cell[2] if cell else None,
            "confidence": None,
        }
        items.append(item)

    uncertain: list[dict] = []
    for table_index, table in enumerate(result.tables):
        for (row, column), raw_score in table.cell_confidence.items():
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                continue
            if (
                not math.isfinite(score)
                or score >= LOW_CONFIDENCE_THRESHOLD
                or (table_index, row, column) in finding_cells
                or not 0 <= row < len(table.rows)
                or not 0 <= column < len(table.rows[row])
            ):
                continue
            sources = (
                table.cell_sources[row][column]
                if row < len(table.cell_sources) and column < len(table.cell_sources[row])
                else []
            )
            page = next(
                (
                    record.get("page")
                    for record in sources
                    if isinstance(record.get("page"), int) and record["page"] > 0
                ),
                table.provenance[row][0][0]
                if row < len(table.provenance) and table.provenance[row]
                else table.page,
            )
            value = str(table.rows[row][column])
            preview = value if len(value) <= 80 else value[:77] + "..."
            uncertain.append(
                {
                    "id": f"confidence-{table_index}-{row}-{column}",
                    "kind": "confidence",
                    "severity": "warning",
                    "page": page,
                    "title": "Low recognition confidence",
                    "reason": (
                        f"OCR confidence is {round(score * 100)}% for {preview!r}; "
                        "compare it with the highlighted source."
                    ),
                    "suggestion": "Inspect the source reading before export.",
                    "table": table_index,
                    "row": row,
                    "column": column,
                    "confidence": score,
                }
            )
    uncertain.sort(
        key=lambda item: (
            item["confidence"],
            item["page"],
            item["table"],
            item["row"],
            item["column"],
        )
    )
    finding_total = len(items)
    uncertain_total = len(uncertain)
    items.extend(uncertain[:LOW_CONFIDENCE_LIMIT])

    checked = 0
    for item in items:
        record = saved.get(item["id"], {})
        if isinstance(record, dict) and record.get("status") == "checked":
            item["status"] = "checked"
            item["checked_at"] = record.get("at")
            checked += 1
        else:
            item["status"] = "pending"
            item["checked_at"] = None
    return {
        "items": items,
        "total": finding_total + uncertain_total,
        "visible": len(items),
        "pending": len(items) - checked,
        "checked": checked,
        "omitted": max(0, uncertain_total - LOW_CONFIDENCE_LIMIT),
        "confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
    }


def set_item_review(result: Result, item_id: str, source_checked: bool) -> Result:
    """Persist one queue decision without changing extracted values or their fingerprint."""
    queue = review_queue(result)
    if item_id not in {item["id"] for item in queue["items"]}:
        raise ValueError("Review queue item is not part of the current extraction.")
    working = deepcopy(result)
    review = deepcopy(working.review)
    records = review.get("item_reviews", {})
    if not isinstance(records, dict):
        records = {}
    if source_checked:
        records[item_id] = {
            "status": "checked",
            "at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        records.pop(item_id, None)
        if review.get("status") == "reviewed":
            previous = {key: value for key, value in review.items() if key != "item_reviews"}
            review = {
                "status": "unreviewed",
                "reason": "A priority review item was reopened.",
                "previous_review": previous,
            }
    review["item_reviews"] = records
    review.setdefault("status", "unreviewed")
    working.review = review
    return working


def apply_edit(result: Result, table: int, row: int, column: int, value: str, note: str) -> Result:
    """Return a new reviewed-work copy; preserve original source readings and history."""
    if not note.strip():
        raise ValueError("Explain the correction after checking the source.")
    if not history_valid(result):
        raise ValueError("Correction history is inconsistent; restore the original extraction.")
    if type(table) is not int or not 0 <= table < len(result.tables):
        raise ValueError("Invalid table index.")
    target = result.tables[table]
    if type(row) is not int or not -1 <= row < len(target.rows):
        raise ValueError("Invalid source row.")
    values = target.headers if row == -1 else target.rows[row]
    if type(column) is not int or not 0 <= column < len(values):
        raise ValueError("Invalid column index.")
    working = deepcopy(result)
    target = working.tables[table]
    old = target.headers[column] if row == -1 else target.rows[row][column]
    if old == str(value):
        raise ValueError("The value is unchanged.")
    event = {
        "at": datetime.now(timezone.utc).isoformat(),
        "table": table,
        "row": row,
        "column": column,
        "before": old,
        "after": str(value),
        "note": note.strip(),
        "previous": working.history[-1]["sha256"]
        if working.history
        else working.source_sha256 or "initial",
    }
    event["sha256"] = digest(event)
    working.history.append(event)
    if row == -1:
        target.headers[column] = str(value)
    else:
        target.rows[row][column] = str(value)
    # Preserve page-level extraction observations; recompute data-dependent rules.
    extraction_codes = {
        "candidate_disagreement",
        "page_failed",
        "no_table",
        "empty_page",
        "inferred_join",
        "split_row_join",
    }
    working.issues = [i for i in working.issues if i.code in extraction_codes]
    for i, t in enumerate(working.tables, 1):
        working.issues.extend(validate(t, i))
    analyze(working)
    working.review = {
        "status": "unreviewed",
        "reason": "Data changed; prior review is no longer current.",
        "previous_review": deepcopy(result.review),
    }
    return working


def complete_review(result: Result, source_checked: bool, note: str) -> Result:
    """Record an explicit source-check attestation for this exact snapshot."""
    if not source_checked:
        raise ValueError("Confirm that you checked the original source pages.")
    if not note.strip():
        raise ValueError("Record your source review and any accepted findings.")
    if not history_valid(result):
        raise ValueError("Correction history is inconsistent.")
    working = deepcopy(result)
    at = datetime.now(timezone.utc).isoformat()
    item_reviews = deepcopy(result.review.get("item_reviews", {}))
    if not isinstance(item_reviews, dict):
        item_reviews = {}
    for item in review_queue(result)["items"]:
        item_reviews[item["id"]] = {"status": "checked", "at": at}
    working.review = {
        "status": "reviewed",
        "at": at,
        "note": note.strip(),
        "acknowledged_findings": len(working.issues),
        "item_reviews": item_reviews,
        "fingerprint": fingerprint(working),
        "meaning": "Human source-check attestation, not independently measured accuracy.",
    }
    return working
