"""Review-only edits, reproducible fingerprints and an append-only change receipt."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone

from .constraints import analyze
from .models import Result
from .validate import validate


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


def apply_edit(result: Result, table: int, row: int, column: int, value: str, note: str) -> Result:
    """Return a new reviewed-work copy; preserve original source readings and history."""
    if not note.strip():
        raise ValueError("Explain the correction after checking the source.")
    if not history_valid(result):
        raise ValueError("Correction history is inconsistent; restore the original extraction.")
    working = deepcopy(result)
    target = working.tables[table]
    if row < -1:
        raise ValueError("Invalid source row.")
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
    working.review = {
        "status": "reviewed",
        "at": datetime.now(timezone.utc).isoformat(),
        "note": note.strip(),
        "acknowledged_findings": len(working.issues),
        "fingerprint": fingerprint(working),
        "meaning": "Human source-check attestation, not independently measured accuracy.",
    }
    return working
