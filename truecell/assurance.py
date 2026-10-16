"""Controlled mutation tests measure validation sensitivity, not OCR accuracy."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal

from .constraints import discover
from .models import Table
from .values import number


def challenge(table: Table, limit: int = 30) -> dict:
    """Perturb numeric cells independently and invoke the production validator.

    Headers are replaced with opaque names, values stay in disposable copies.
    Unsupported arithmetic can be missed and remains visible in the results.
    """
    relations = discover(table)
    from .validate import total_row, validate
    from .values import is_identifier

    def signature(issue):
        return issue.code, issue.page, issue.row, issue.column

    # Hide all original labels: this tests the same content-led validator used
    # by conversion, not a synthetic check that is guaranteed to pass.
    baseline = deepcopy(table)
    baseline.headers = [f"C{c + 1}" for c in range(len(table.headers))]
    before = {signature(i) for i in validate(baseline)}
    candidates = [
        (r, c)
        for r, row in enumerate(table.rows)
        if not total_row(row)
        for c, value in enumerate(row)
        if number(value) is not None and not is_identifier(value)
    ]
    candidates.sort(key=lambda rc: hashlib.sha256(f"{rc}".encode()).hexdigest())
    checks = []
    for r, c in candidates[:limit]:
        original = number(table.rows[r][c])
        mutated = original + Decimal("7.13")
        disposable = deepcopy(baseline)
        disposable.rows[r][c] = str(mutated)
        added = [i for i in validate(disposable) if signature(i) not in before]
        checks.append(
            {
                "row": r + 1,
                "column": c + 1,
                "original": str(original),
                "mutated": str(mutated),
                "caught": bool(added),
                "new_findings": sorted({i.code for i in added}),
            }
        )
    supported = {c for rel in relations for c in rel["columns"]}
    return {
        "scope": "Arithmetic validator only. This does not test OCR or general hidden-document accuracy.",
        "tested": len(checks),
        "caught": sum(c["caught"] for c in checks),
        "cases": checks,
        "unmodeled_columns": [i + 1 for i in range(len(table.headers)) if i not in supported],
        "baseline_sha256": hashlib.sha256(
            json.dumps(table.rows, ensure_ascii=False).encode()
        ).hexdigest(),
    }
