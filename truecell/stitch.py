"""Join adjacent compatible tables without dropping duplicate business records."""
from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher

from .models import Issue, Table
from .table import clean


def compatible(left: Table, right: Table) -> bool:
    """Require adjacent pages, matching shape, x-span and compatible headers."""
    last_page = max(p for sources in left.provenance for p, _ in sources) if left.rows else left.page
    if right.page != last_page + 1 or len(left.headers) != len(right.headers):
        return False
    width = max(1, left.bbox[2] - left.bbox[0])
    if max(abs(left.bbox[i] - right.bbox[i]) for i in (0, 2)) / width > .08:
        return False
    if not right.header_detected:
        return True
    a, b = [clean(c).lower() for c in left.headers], [clean(c).lower() for c in right.headers]
    return sum(SequenceMatcher(None, x, y).ratio() > .85 for x, y in zip(a, b)) / len(a) >= .85


def stitch(tables: list[Table]) -> tuple[list[Table], list[Issue]]:
    """Keep source row provenance and flag inferred joins for human review."""
    joined: list[Table] = []
    issues: list[Issue] = []
    for source in tables:
        table = deepcopy(source)
        matches = [t for t in joined if compatible(t, table)]
        if len(matches) != 1:
            joined.append(table)
            continue
        target = matches[0]
        if not table.header_detected:
            issues.append(Issue("warning", table.page, 1, None,
                                "Headerless continuation joined by column count and horizontal span.",
                                code="inferred_join", table=joined.index(target) + 1))
        offset = len(target.rows)
        # Join complementary page-break fragments only with strong structural evidence.
        if (target.rows and table.rows and len(target.rows[-1]) == len(table.headers)
                and len(table.rows[0]) == len(table.headers)):
            before, after = target.rows[-1], table.rows[0]
            tail_holes = [c for c in range(1, len(before)) if not before[c]]
            filled = [c for c in tail_holes if after[c]]
            overlaps = [c for c in range(1, len(before)) if before[c] and after[c]]
            from .values import kind
            if (before[0] and not after[0] and len(filled) >= 2
                    and overlaps and all(kind(before[c]) == kind(after[c]) == "text" for c in overlaps)):
                for c in range(len(before)):
                    before[c] = clean(before[c] + " " + after[c])
                target.provenance[-1].extend(table.provenance[0])
                target.row_engines[-1] += "+" + table.row_engines[0]
                issues.append(Issue("warning", table.page, table.provenance[0][0][1], None,
                    "Complementary page-break row fragments merged; verify the reconstructed record.",
                    code="split_row_join", table=joined.index(target) + 1))
                table.rows.pop(0)
                table.provenance.pop(0)
                table.row_engines.pop(0)
                table.cell_confidence = {(r-1,c):v for (r,c),v in table.cell_confidence.items() if r > 0}
        target.rows.extend(table.rows)
        target.provenance.extend(table.provenance)
        target.row_engines.extend(table.row_engines)
        if table.engine not in target.engine.split("+"):
            target.engine += "+" + table.engine
        for (r, c), confidence in table.cell_confidence.items():
            target.cell_confidence[(r + offset, c)] = confidence
        target.notes.extend(note for note in table.notes if note not in target.notes)
        target.confidence = min(target.confidence, table.confidence)
    return joined, issues
