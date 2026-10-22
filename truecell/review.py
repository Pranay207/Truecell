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
DEFAULT_REVIEW_PAGE_SIZE = 100
MAX_REVIEW_PAGE_SIZE = 500


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
        and review_queue(result, limit=1)["pending"] == 0
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


def _valid_bbox(record: object) -> bool:
    """Return whether a source record contains a finite, non-empty rectangle."""
    if not isinstance(record, dict):
        return False
    bbox = record.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return False
    try:
        x0, y0, x1, y1 = (float(value) for value in bbox)
    except (TypeError, ValueError):
        return False
    return all(math.isfinite(value) for value in (x0, y0, x1, y1)) and x1 > x0 and y1 > y0


def evidence_status(value: object, sources: object, fallback_page: int | None = None) -> dict:
    """Describe the source-location coverage of one extracted cell.

    Empty cells are outside the evidence invariant. Every non-empty cell is either
    located by at least one source box or carries an explicit reason explaining why
    it must be checked against the full source page.
    """
    text = "" if value is None else str(value)
    records = (
        [record for record in sources if isinstance(record, dict)]
        if isinstance(sources, list)
        else []
    )
    # Comparison records are deliberately retained for alternative-reading UI,
    # but they do not locate or support the current working value.  Counting a
    # comparison box here could falsely label an unlocated primary reading as
    # exact cell evidence.
    supporting_records = [record for record in records if record.get("role") != "comparison"]
    pages = sorted(
        {
            record["page"]
            for record in supporting_records
            if isinstance(record.get("page"), int) and record["page"] > 0
        }
    )
    page = pages[0] if pages else fallback_page
    if not text.strip():
        return {
            "status": "not_applicable",
            "evidence_state": "empty_cell",
            "located": False,
            "reason": "The extracted cell is empty; no source location is required.",
            "page": page,
            "source_records": len(supporting_records),
            "located_records": 0,
        }
    located = sum(_valid_bbox(record) for record in supporting_records)
    if located:
        reason = "At least one original reading has an exact source bounding box."
        status = "located"
        state = "exact_source_box"
    elif supporting_records:
        reason = (
            "The extraction engine retained a source reading but did not return an exact "
            "cell bounding box; inspect the full source page."
        )
        status = "unlocated"
        state = "page_only_review"
    else:
        reason = (
            "No cell-level source record was produced; inspect the mapped source page "
            "before accepting this value."
        )
        status = "unlocated"
        state = "page_only_review"
    return {
        "status": status,
        "evidence_state": state,
        "located": bool(located),
        "reason": reason,
        "page": page,
        "source_records": len(supporting_records),
        "located_records": located,
    }


def confidence_evidence(record: object | None, fallback_score: object = None) -> dict:
    """Describe what a recognition score means without inventing native confidence.

    Native PDF text has deterministic text/geometry evidence but no probabilistic
    OCR score.  Keeping that state explicit prevents a missing score from being
    mistaken for either zero or perfect confidence.
    """
    source = record if isinstance(record, dict) else {}
    engine = str(source.get("engine") or "unknown")
    raw_score = source.get("confidence", fallback_score)
    try:
        score = float(raw_score) if raw_score is not None else None
    except (TypeError, ValueError):
        score = None
    if score is not None and math.isfinite(score):
        score = max(0.0, min(1.0, score))
        return {
            "kind": "ocr_score" if not engine.startswith("native") else "engine_score",
            "score": score,
            "label": f"{round(score * 100)}% recognition score",
            "engine": engine,
            "meaning": "Engine-reported recognition confidence; not measured accuracy.",
        }
    if engine.startswith("native"):
        return {
            "kind": "native_text",
            "score": None,
            "label": "Native PDF text (no OCR score)",
            "engine": engine,
            "meaning": "Text and geometry came directly from the PDF text layer.",
        }
    return {
        "kind": "not_reported",
        "score": None,
        "label": "Recognition score unavailable",
        "engine": engine,
        "meaning": "The source record does not contain an engine confidence score.",
    }


def cell_evidence(result: Result, table: int, row: int, column: int) -> dict:
    """Return one complete, deterministic evidence envelope for a displayed cell."""
    if type(table) is not int or not 0 <= table < len(result.tables):
        raise ValueError("Invalid table index.")
    target = result.tables[table]
    if type(row) is not int or not -1 <= row < len(target.rows):
        raise ValueError("Invalid source row.")
    values = target.headers if row == -1 else target.rows[row]
    if type(column) is not int or not 0 <= column < len(values):
        raise ValueError("Invalid column index.")

    if row == -1:
        raw_records = target.header_sources[column] if column < len(target.header_sources) else []
        fallback_page = target.page
        fallback_score = None
        reference = f"T{table + 1}:H:C{column + 1}"
    else:
        source_row = target.cell_sources[row] if row < len(target.cell_sources) else []
        raw_records = source_row[column] if column < len(source_row) else []
        fallback_page = (
            target.provenance[row][0][0]
            if row < len(target.provenance) and target.provenance[row]
            else target.page
        )
        fallback_score = target.cell_confidence.get((row, column))
        reference = f"T{table + 1}:R{row + 1}:C{column + 1}"

    records = [dict(record) for record in raw_records if isinstance(record, dict)]
    for record in records:
        record["confidence_evidence"] = confidence_evidence(record, fallback_score)
    primary = next((record for record in records if record.get("role") != "comparison"), None)
    confidence = confidence_evidence(primary, fallback_score)
    value = str(values[column])
    history = [
        dict(event)
        for event in result.history
        if event.get("table") == table and event.get("row") == row and event.get("column") == column
    ]
    original_value = str(history[0].get("before", value)) if history else value
    original_reading = original_value
    contributing_readings: list[str] = []
    for record in records:
        if record.get("role") == "comparison":
            continue
        reading = str(
            record.get("initial_reading")
            if record.get("initial_reading") is not None
            else record.get("text", "")
        ).strip()
        if reading and (
            not contributing_readings or reading.casefold() != contributing_readings[-1].casefold()
        ):
            contributing_readings.append(reading)
    if contributing_readings:
        original_reading = " | ".join(contributing_readings)

    alternatives: list[dict] = []
    seen: set[tuple[str, str, int | None]] = set()
    for record in records:
        candidates = []
        if record.get("role") == "comparison":
            candidates.append((record.get("text"), "comparison"))
        initial = record.get("initial_reading")
        if initial is not None and str(initial) != str(record.get("text", "")):
            candidates.append((initial, "initial_reading"))
        for reading, kind in candidates:
            text = "" if reading is None else str(reading)
            page = record.get("page") if isinstance(record.get("page"), int) else None
            key = (text, str(record.get("engine") or "unknown"), page)
            if not text or key in seen:
                continue
            seen.add(key)
            alternatives.append(
                {
                    "text": text,
                    "kind": kind,
                    "engine": record.get("engine") or "unknown",
                    "page": page,
                    "bbox": record.get("bbox"),
                    "confidence": record["confidence_evidence"],
                }
            )

    return {
        "evidence_id": reference,
        "cell": {
            "table": table,
            "row": row,
            "column": column,
            "kind": "header" if row == -1 else "data",
        },
        "value": value,
        "original_value": original_value,
        "original_reading": original_reading,
        "sources": records,
        "alternative_readings": alternatives,
        "confidence": confidence,
        "location": evidence_status(value, records, fallback_page),
        "correction_history": history,
        "correction_count": len(history),
    }


def evidence_coverage(result: Result) -> dict:
    """Account for the evidence state of every non-empty header and data cell."""
    total = located = unlocated = 0
    by_table: list[dict] = []
    for table_index, table in enumerate(result.tables):
        table_total = table_located = table_unlocated = 0
        for column, value in enumerate(table.headers):
            sources = table.header_sources[column] if column < len(table.header_sources) else []
            status = evidence_status(value, sources, table.page)
            if status["status"] == "not_applicable":
                continue
            table_total += 1
            table_located += int(status["located"])
            table_unlocated += int(not status["located"])
        for row, values in enumerate(table.rows):
            fallback = (
                table.provenance[row][0][0]
                if row < len(table.provenance) and table.provenance[row]
                else table.page
            )
            source_row = table.cell_sources[row] if row < len(table.cell_sources) else []
            for column, value in enumerate(values):
                sources = source_row[column] if column < len(source_row) else []
                status = evidence_status(value, sources, fallback)
                if status["status"] == "not_applicable":
                    continue
                table_total += 1
                table_located += int(status["located"])
                table_unlocated += int(not status["located"])
        total += table_total
        located += table_located
        unlocated += table_unlocated
        by_table.append(
            {
                "table": table_index,
                "nonempty_cells": table_total,
                "located": table_located,
                "unlocated": table_unlocated,
                "coverage": table_located / table_total if table_total else 1.0,
            }
        )
    return {
        "nonempty_cells": total,
        "located": located,
        "unlocated": unlocated,
        "coverage": located / total if total else 1.0,
        "complete": unlocated == 0,
        "by_table": by_table,
        "invariant": "Every non-empty cell is located or explicitly marked unlocated.",
    }


def _review_items(result: Result) -> list[dict]:
    """Build the complete source-addressable queue without truncating any category."""
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
                or not str(table.rows[row][column]).strip()
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

    evidence_items: list[dict] = []
    for table_index, table in enumerate(result.tables):
        for column, value in enumerate(table.headers):
            sources = table.header_sources[column] if column < len(table.header_sources) else []
            location = evidence_status(value, sources, table.page)
            if location["status"] != "unlocated":
                continue
            evidence_items.append(
                {
                    "id": f"evidence-{table_index}-header-{column}",
                    "kind": "evidence",
                    "severity": "warning",
                    "page": location["page"] or table.page,
                    "title": "Header source box unavailable",
                    "reason": location["reason"],
                    "suggestion": "Inspect the full source page before accepting this header.",
                    "table": table_index,
                    "row": -1,
                    "column": column,
                    "confidence": None,
                }
            )
        for row, values in enumerate(table.rows):
            fallback = (
                table.provenance[row][0][0]
                if row < len(table.provenance) and table.provenance[row]
                else table.page
            )
            source_row = table.cell_sources[row] if row < len(table.cell_sources) else []
            for column, value in enumerate(values):
                sources = source_row[column] if column < len(source_row) else []
                location = evidence_status(value, sources, fallback)
                if location["status"] != "unlocated":
                    continue
                evidence_items.append(
                    {
                        "id": f"evidence-{table_index}-{row}-{column}",
                        "kind": "evidence",
                        "severity": "warning",
                        "page": location["page"] or table.page,
                        "title": "Cell source box unavailable",
                        "reason": location["reason"],
                        "suggestion": "Inspect the full source page before accepting this value.",
                        "table": table_index,
                        "row": row,
                        "column": column,
                        "confidence": None,
                    }
                )

    items.extend(evidence_items)
    items.extend(uncertain)

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
    kind_order = {"finding": 0, "evidence": 1, "confidence": 2}
    items.sort(
        key=lambda item: (
            item["status"] == "checked",
            kind_order.get(item["kind"], 9),
            item.get("confidence") if item.get("confidence") is not None else 1.0,
            item.get("page") or 0,
            item.get("table") if item.get("table") is not None else -1,
            item.get("row") if item.get("row") is not None else -2,
            item.get("column") if item.get("column") is not None else -1,
            item["id"],
        )
    )
    return items


def review_queue(
    result: Result,
    *,
    offset: int = 0,
    limit: int | None = DEFAULT_REVIEW_PAGE_SIZE,
    table: int | None = None,
    status: str | None = None,
) -> dict:
    """Return an explicit page of the complete review queue and global totals."""
    if type(offset) is not int or offset < 0:
        raise ValueError("Review queue offset must be a non-negative integer.")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= MAX_REVIEW_PAGE_SIZE):
        raise ValueError(f"Review queue limit must be between 1 and {MAX_REVIEW_PAGE_SIZE}.")
    if table is not None and (type(table) is not int or table < 0):
        raise ValueError("Review queue table must be a non-negative integer.")
    if status not in {None, "pending", "checked"}:
        raise ValueError("Review queue status must be pending or checked.")

    all_items = _review_items(result)
    checked = sum(item["status"] == "checked" for item in all_items)
    filtered = [
        item
        for item in all_items
        if (table is None or item.get("table") in {None, table})
        and (status is None or item["status"] == status)
    ]
    page = filtered[offset:] if limit is None else filtered[offset : offset + limit]
    next_offset = offset + len(page)
    remaining = max(0, len(filtered) - next_offset)
    return {
        "items": page,
        "total": len(all_items),
        "visible": len(page),
        "pending": len(all_items) - checked,
        "checked": checked,
        "filtered_total": len(filtered),
        "filtered_pending": sum(item["status"] == "pending" for item in filtered),
        "offset": offset,
        "limit": limit,
        "remaining": remaining,
        "has_more": remaining > 0,
        "next_offset": next_offset if remaining else None,
        # Kept for older clients, but now means an explicitly reported next page.
        "omitted": remaining,
        "confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
    }


def quality_state(result: Result) -> dict:
    """Return a user-facing quality gate without replacing the job lifecycle state."""
    reasons: list[str] = []
    if any(page.error for page in result.pages):
        reasons.append("One or more pages failed and should be rescanned or retried.")
    has_data = any(
        str(value).strip() for table in result.tables for row in table.rows for value in row
    )
    if not result.tables or not has_data:
        reasons.append("No usable table data was reconstructed.")
    if reasons:
        state = "needs_rescan"
    else:
        queue = review_queue(result, limit=1)
        if review_current(result) and queue["pending"] == 0:
            state = "reviewed"
        else:
            state = "needs_review"
            if queue["pending"]:
                reasons.append(f"{queue['pending']} review item(s) remain unresolved.")
            else:
                reasons.append("A human source-check attestation has not been recorded.")
    return {
        "status": state,
        "reasons": reasons,
        "reviewed_export_ready": state == "reviewed",
        "draft_export_ready": bool(result.tables),
    }


def set_item_review(result: Result, item_id: str, source_checked: bool) -> Result:
    """Persist one queue decision without changing extracted values or their fingerprint."""
    queue = review_queue(result, limit=None)
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
    queue = review_queue(result, limit=None)
    if queue["pending"]:
        raise ValueError(
            f"Review each actionable item individually before completing the source check "
            f"({queue['pending']} pending)."
        )
    working = deepcopy(result)
    at = datetime.now(timezone.utc).isoformat()
    item_reviews = deepcopy(result.review.get("item_reviews", {}))
    if not isinstance(item_reviews, dict):
        item_reviews = {}
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
