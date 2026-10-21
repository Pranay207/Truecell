"""Learn content-based equations and produce explicit counterfactual repair evidence.

Agreement is empirical support on this document, never an accuracy probability.
No proposal is applied here. A source document can itself be arithmetically wrong.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from itertools import combinations, permutations
from typing import Any

from .models import Result, Table
from .semantics import infer_column_semantics
from .values import is_identifier, number

EPSILON = Decimal("0.01")


def _numeric_columns(table: Table) -> list[int]:
    semantics = infer_column_semantics(table)
    columns = []
    for c in range(len(table.headers)):
        values = [row[c] for row in table.rows if c < len(row) and row[c] and not _total(row)]
        if (
            semantics[c].role not in {"id", "phone", "date"}
            and values
            and sum(number(v) is not None and not is_identifier(v) for v in values) / len(values)
            >= 0.75
        ):
            columns.append(c)
    priority = {"quantity": 0, "amount": 1, "total": 1, "balance": 2, "text": 3}
    return sorted(columns, key=lambda c: (priority.get(semantics[c].role, 3), c))[:14]


def _total(row: list[str]) -> bool:
    from .validate import total_row

    return total_row(row)


def _value(table: Table, r: int, c: int) -> Decimal | None:
    if r < 0 or r >= len(table.rows) or c >= len(table.rows[r]):
        return None
    return number(table.rows[r][c])


def discover(table: Table, table_index: int = 1) -> list[dict[str, Any]]:
    """Discover varied row equations and a strongest running-balance relation."""
    columns = _numeric_columns(table)
    semantics = infer_column_semantics(table)
    relations = []
    rows = [r for r, row in enumerate(table.rows) if not _total(row)]
    for a, b in combinations(columns, 2):
        for z in columns:
            if z in (a, b):
                continue
            for operator in ("*", "+"):
                evidence = []
                for r in rows:
                    x, y, v = (_value(table, r, c) for c in (a, b, z))
                    if None in (x, y, v) or x == 0 or y == 0:
                        continue
                    expected = x * y if operator == "*" else x + y
                    evidence.append((r, abs(v - expected) <= EPSILON, expected, x, y, v))
                if len(evidence) < 5 or len({(e[3], e[4]) for e in evidence}) < 4:
                    continue
                matched = sum(e[1] for e in evidence)
                if matched / len(evidence) < 0.8:
                    continue
                relations.append(
                    {
                        "id": f"T{table_index}:C{a + 1}{operator}C{b + 1}=C{z + 1}",
                        "table": table_index,
                        "kind": "row",
                        "operator": operator,
                        "columns": [a, b, z],
                        "formula": f"{table.headers[a]} {operator} {table.headers[b]} = {table.headers[z]}",
                        "checked": len(evidence),
                        "matched": matched,
                        "support": matched / len(evidence),
                        "rows": [e[0] for e in evidence],
                        "violations": [
                            {
                                "row": e[0],
                                "column": z,
                                "observed": str(e[5]),
                                "expected": str(e[2]),
                            }
                            for e in evidence
                            if not e[1]
                        ],
                    }
                )
    balances = []
    named_balances = [c for c in columns if semantics[c].role == "balance"]
    for balance in named_balances or columns[:12]:
        for debit, credit in permutations([c for c in columns[:12] if c != balance], 2):
            evidence = []
            for r in rows:
                if r == 0 or _total(table.rows[r - 1]):
                    continue
                before, after, outflow, inflow = (
                    _value(table, rr, cc)
                    for rr, cc in [
                        (r - 1, balance),
                        (r, balance),
                        (r, debit),
                        (r, credit),
                    ]
                )
                if None in (before, after, outflow, inflow):
                    continue
                expected = before - outflow + inflow
                evidence.append(
                    (
                        r,
                        abs(after - expected) <= EPSILON,
                        expected,
                        after,
                        before != after,
                    )
                )
            if len(evidence) < 6 or sum(e[4] for e in evidence) < 4:
                continue
            matched = sum(e[1] for e in evidence)
            if matched / len(evidence) >= 0.7:
                balances.append(
                    {
                        "id": f"T{table_index}:balance:C{balance + 1}-C{debit + 1}+C{credit + 1}",
                        "table": table_index,
                        "kind": "balance",
                        "operator": "balance",
                        "columns": [balance, debit, credit],
                        "formula": f"Previous {table.headers[balance]} - {table.headers[debit]} + {table.headers[credit]} = {table.headers[balance]}",
                        "checked": len(evidence),
                        "matched": matched,
                        "support": matched / len(evidence),
                        "rows": [e[0] for e in evidence],
                        "violations": [
                            {
                                "row": e[0],
                                "column": balance,
                                "expected": str(e[2]),
                                "observed": str(e[3]),
                            }
                            for e in evidence
                            if not e[1]
                        ],
                    }
                )
    if balances:
        relations.append(max(balances, key=lambda v: v["support"]))
    return relations


def _counterfactuals(table: Table, relation: dict) -> list[tuple[int, int, Decimal, str]]:
    output = []
    for violation in relation["violations"]:
        r = violation["row"]
        equation = f"{relation['id']}@row{r + 1}"
        if relation["kind"] == "row":
            a, b, z = relation["columns"]
            x, y, v = (_value(table, r, c) for c in (a, b, z))
            if None in (x, y, v):
                continue
            if relation["operator"] == "+":
                candidates = [(a, v - y), (b, v - x), (z, x + y)]
            else:
                candidates = [(z, x * y)]
                if y:
                    candidates.append((a, v / y))
                if x:
                    candidates.append((b, v / x))
            output.extend((r, c, val, equation) for c, val in candidates)
        else:
            balance, debit, credit = relation["columns"]
            previous, current, d, c = (
                _value(table, rr, cc)
                for rr, cc in [(r - 1, balance), (r, balance), (r, debit), (r, credit)]
            )
            if None not in (previous, current, d, c):
                output.extend(
                    [
                        (r, balance, previous - d + c, equation),
                        (r - 1, balance, current + d - c, equation),
                        (r, debit, previous + c - current, equation),
                        (r, credit, current - previous + d, equation),
                    ]
                )
    return output


def propose(table: Table, relations: list[dict], table_index: int = 1) -> list[dict]:
    """Rank candidate single-cell changes by independent broken equations repaired."""
    votes = defaultdict(set)
    for relation in relations:
        for r, c, value, equation in _counterfactuals(table, relation):
            # Only amounts expressible at cent precision are presented. Ratios
            # with long recurring decimals do not become misleading exact fixes.
            rounded = value.quantize(Decimal("0.01"))
            if abs(rounded - value) > Decimal("0.000001"):
                continue
            if _value(table, r, c) is None or abs(_value(table, r, c) - rounded) <= EPSILON:
                continue
            votes[(r, c, rounded)].add(equation)
    proposals = []
    for (r, c, value), equations in votes.items():
        proposals.append(
            {
                "id": f"T{table_index}:R{r + 1}:C{c + 1}:{value}",
                "table": table_index,
                "row": r,
                "column": c,
                "observed": table.rows[r][c],
                "proposed": str(value),
                "supporting_equations": sorted(equations),
                "support_count": len(equations),
                "source_pages": sorted({p for p, _ in table.provenance[r]}),
                "status": "proposal_only",
                "basis": "Inferred document arithmetic; verify the source before applying.",
                "alternatives": len({v for rr, cc, v in votes if rr == r and cc == c}),
            }
        )
    return sorted(proposals, key=lambda p: (-p["support_count"], p["row"], p["column"]))


def analyze(result: Result) -> None:
    """Attach reproducible equation receipts and review-only repair proposals."""
    result.constraints = []
    result.proposals = []
    for i, table in enumerate(result.tables, 1):
        relations = discover(table, i)
        result.constraints.extend(relations)
        result.proposals.extend(propose(table, relations, i))


def coverage(result: Result) -> dict[str, int]:
    """Report observable evidence counts without fabricating an accuracy score."""
    cells = sum(len(row) for t in result.tables for row in t.rows)
    located = sum(
        bool(sources and any(s.get("bbox") for s in sources))
        for t in result.tables
        for row in t.cell_sources
        for sources in row
    )
    return {
        "cells": cells,
        "cells_with_source_boxes": located,
        "equations": len(result.constraints),
        "equation_checks": sum(r["checked"] for r in result.constraints),
        "failed_equation_checks": sum(len(r["violations"]) for r in result.constraints),
        "proposals_with_multiple_equations": sum(p["support_count"] >= 2 for p in result.proposals),
    }
