"""Header-guided native layout reconstruction, including sparse text tables.

Uses font and whitespace evidence, not filename-specific templates. A blank
column remains a column; continuation lines remain attached to their record.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from statistics import median

from .models import Table
from .values import kind, number


def lines_of(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    height = median(w["bottom"] - w["top"] for w in words) if words else 10
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - median(w["top"] for w in lines[-1])) < height * 0.55:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def phrases(line: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    h = median(w["bottom"] - w["top"] for w in line)
    for word in line:
        if groups and word["x0"] - groups[-1][-1]["x1"] < max(4, h * 0.7):
            groups[-1].append(word)
        else:
            groups.append([word])
    return groups


def text(words: list[dict]) -> str:
    return " ".join(w["text"] for line in lines_of(words) for w in line)


def bounds(words: list[dict]) -> list[float] | None:
    if not words:
        return None
    return [
        min(w["x0"] for w in words),
        min(w["top"] for w in words),
        max(w["x1"] for w in words),
        max(w["bottom"] for w in words),
    ]


def evidence(words: list[dict], page: int, engine: str) -> list[dict]:
    return (
        [
            {
                "page": page,
                "bbox": bounds(words),
                "text": text(words),
                "engine": engine,
                "confidence": min((w.get("confidence", 0) for w in words), default=0)
                if engine.startswith("ocr-")
                else None,
                "coordinates": "page points",
            }
        ]
        if words
        else []
    )


def _header(line: list[dict]) -> bool:
    if len(phrases(line)) < 2:
        return False
    if sum("bold" in w.get("fontname", "").lower() for w in line) < len(line) * 0.75:
        return False
    # Years can label a financial column; an ordinary bold total is not a header.
    return all(
        number("".join(w["text"].split())) is None or re.fullmatch(r"(?:19|20)\d{2}", w["text"])
        for w in line
    )


def _cut(left: list[dict], right: list[dict], body: list[dict], height: float) -> float:
    low, high = max(w["x1"] for w in left) + 1, min(w["x0"] for w in right) - 1
    if high <= low:
        return (low + high) / 2
    intervals = sorted(
        (max(low, w["x0"]), min(high, w["x1"])) for w in body if w["x1"] > low and w["x0"] < high
    )
    gaps = []
    cursor = low
    for a, b in intervals:
        if a - cursor > height * 0.45:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if high - cursor > height * 0.45:
        gaps.append((cursor, high))
    center = (low + high) / 2
    if not gaps:
        return center
    a, b = min(gaps, key=lambda g: abs((g[0] + g[1]) / 2 - center))
    return (a + b) / 2


def header_tables(
    words: list[dict], page: int, *, engine: str = "native-anchors", font_evidence: bool = True
) -> list[Table]:
    """Rebuild columns from font-backed or repeated OCR header evidence."""
    if len(words) < 8:
        return []
    lines = lines_of(words)
    height = median(w["bottom"] - w["top"] for w in words)

    def candidate(i, line):
        if font_evidence:
            return _header(line)
        # OCR has no font metadata. Require a separated textual header followed
        # by several numeric records; a page title alone is insufficient.
        if len(phrases(line)) < 3 or any(number(w["text"]) is not None for w in line):
            return False
        following = lines[i + 1 : i + 6]
        return sum(sum(number(w["text"]) is not None for w in row) >= 2 for row in following) >= 3

    candidates = [i for i, line in enumerate(lines) if candidate(i, line)]
    # A finer leaf header immediately below a group header owns the columns.
    candidates = [
        i
        for i in candidates
        if not any(
            0 < lines[j][0]["top"] - lines[i][0]["top"] < height * 2.5
            and len(phrases(lines[j])) > len(phrases(lines[i]))
            for j in candidates
        )
    ]
    output = []
    for ci, index in enumerate(candidates):
        groups = phrases(lines[index])
        count = len(groups)
        end = candidates[ci + 1] if ci + 1 < len(candidates) else len(lines)
        body_lines = lines[index + 1 : end]
        if len(body_lines) < 2:
            continue
        # Page numbers and distant footnotes cannot extend a table indefinitely.
        limited = []
        previous = max(w["bottom"] for w in lines[index])
        for line in body_lines:
            if min(w["top"] for w in line) - previous > height * 6:
                break
            if re.fullmatch(
                r"page\s*\d+(?:\s*(?:of|/)\s*\d+)?|\d+\s*(?:of|/)\s*\d+", text(line), re.I
            ):
                continue
            limited.append(line)
            previous = max(w["bottom"] for w in line)
        body = [w for line in limited for w in line]
        if not body:
            continue
        cuts = [_cut(a, b, body, height) for a, b in zip(groups, groups[1:])]
        headers = [text(g) for g in groups]
        row_words = []
        wrapped_cells: set[tuple[int, int]] = set()
        summaries = []
        last_y = 0.0
        for line in limited:
            cells = [[] for _ in range(count)]
            for word in line:
                cells[bisect_right(cuts, (word["x0"] + word["x1"]) / 2)].append(word)
            occupied = [c for c, cell in enumerate(cells) if cell]
            if not occupied:
                continue
            if not cells[0] and re.search(r"\b(?:brought|carried)\s+forward\b", text(line), re.I):
                summaries.append(
                    {
                        "page": page,
                        "text": text(line),
                        "bbox": bounds(line),
                        "role": "page continuity summary",
                    }
                )
                continue
            y = min(w["top"] for w in line)
            # A missing key plus a small number of nearby text fields can be a
            # wrapped continuation. Requiring an established key and matching
            # populated text columns keeps this reconstruction conservative.
            if (
                row_words
                and not cells[0]
                and 1 <= len(occupied) <= min(2, max(1, count // 3))
                and row_words[-1][0]
                and all(kind(text(cells[c])) == "text" for c in occupied)
                and all(row_words[-1][c] for c in occupied)
                and y - last_y < height * 1.8
            ):
                for c in occupied:
                    row_words[-1][c].extend(cells[c])
                    wrapped_cells.add((len(row_words) - 1, c))
            else:
                row_words.append(cells)
            last_y = y
        if sum(sum(bool(c) for c in row) >= 2 for row in row_words) < 2:
            continue
        rows = [[text(cell) for cell in row] for row in row_words]
        table = Table(
            headers,
            rows,
            page,
            tuple(bounds(lines[index] + body)),
            engine,
            0.92 if font_evidence else min(0.92, median(w.get("confidence", 0) for w in body)),
            True,
        )
        table.header_sources = [evidence(g, page, table.engine) for g in groups]
        table.cell_sources = [
            [evidence(cell, page, table.engine) for cell in row] for row in row_words
        ]
        for r, c in wrapped_cells:
            for record in table.cell_sources[r][c]:
                record["role"] = "wrapped_continuation_join"
        table.page_summaries = summaries
        if not font_evidence:
            for r, row in enumerate(row_words):
                for c, cell in enumerate(row):
                    score = min((w.get("confidence", 0) for w in cell), default=0)
                    table.cell_confidence[r, c] = score
                    for record in table.cell_sources[r][c]:
                        record["confidence"] = score
            for c, cell in enumerate(groups):
                for record in table.header_sources[c]:
                    record["confidence"] = min(w.get("confidence", 0) for w in cell)
        table.notes.append(
            "Header anchors and repeated word positions inferred column boundaries; review alignment."
        )
        if summaries:
            table.notes.append(
                "Page carry-forward summaries retained separately from business rows."
            )
        if not font_evidence:
            table.notes.append(
                "OCR header inferred from geometry and numeric records; verify source text."
            )
        if wrapped_cells:
            table.notes.append(
                "Nearby text-only continuation lines joined to keyed rows; source boxes retained."
            )
        output.append(table)
    return output


def append_summaries(table: Table, words: list[dict]) -> None:
    """Retain nearby unruled invoice totals below a ruled body, with source boxes."""
    if not table.rows:
        return
    descriptions = [
        c
        for c in range(len(table.headers))
        if sum(kind(row[c]) == "text" for row in table.rows if c < len(row)) > len(table.rows) * 0.5
    ]
    if not descriptions:
        return
    # An alphanumeric record key is also classified as text. Prefer the
    # descriptive field rather than projecting totals into that key column.
    label_column = max(
        descriptions,
        key=lambda c: median(len(row[c]) for row in table.rows if c < len(row) and row[c]),
    )
    h = median(w["bottom"] - w["top"] for w in words) if words else 10
    below = [
        w
        for w in words
        if table.bbox[3] - 1 <= w["top"] <= table.bbox[3] + h * 14
        and table.bbox[0] - h <= w["x0"] <= table.bbox[2] + h
    ]
    right_edges = []
    for c in range(len(table.headers)):
        boxes = [s["bbox"] for row in table.cell_sources for s in row[c] if s.get("bbox")]
        right_edges.append(median(b[2] for b in boxes) if boxes else table.bbox[2])
    for line in lines_of(below):
        value_words = [
            w for w in line if number(w["text"]) is not None and not w["text"].endswith("%")
        ]
        labels = [w for w in line if w not in value_words]
        label = text(labels)
        if not re.search(
            r"\b(?:total|tax|gst|vat|discount|round(?:ing)?|freight|shipping)\b", label, re.I
        ):
            break
        if not value_words or len(label.split()) > 8:
            break
        cells = [[] for _ in table.headers]
        cells[label_column] = labels
        for word in value_words:
            column = min(range(len(right_edges)), key=lambda c: abs(right_edges[c] - word["x1"]))
            if column == label_column:
                break
            cells[column].append(word)
        else:
            table.rows.append([text(c) for c in cells])
            table.cell_sources.append([evidence(c, table.page, table.engine) for c in cells])
            table.provenance.append([(table.page, len(table.provenance) + 1)])
            table.row_engines.append(table.engine)
            note = (
                "Unruled summary below the table retained; label projected into the descriptive "
                "column. Verify the source."
            )
            if note not in table.notes:
                table.notes.append(note)
            continue
        break
