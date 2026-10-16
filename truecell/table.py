"""Table normalization, conservative headers and word-box reconstruction."""

from __future__ import annotations

import re
from collections import Counter
from statistics import median

from .models import Table
from .values import kind

FOOTER = re.compile(r"^(?:page\s*)?\d+\s*(?:of|/)\s*\d+$|^page\s+\d+$", re.I)


def clean(value: object) -> str:
    """Normalize whitespace while preserving all non-whitespace characters."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def header_likely(first: list[str], following: list[list[str]]) -> bool:
    """Detect a textual header only when later contents provide evidence."""
    if not following:
        return False
    text = sum(kind(c) == "text" for c in first)
    if text < max(1, len(first) * 0.6):
        return False
    changes = sum(
        kind(first[c]) == "text"
        and any(
            c < len(row) and kind(row[c]) in {"numeric", "currency", "date", "id"}
            for row in following[:5]
        )
        for c in range(len(first))
    )
    return changes >= max(1, len(first) * 0.2)


def normalize(
    raw: list[list[object]],
    page: int,
    bbox: tuple,
    engine: str,
    confidence: float = 1.0,
    cell_boxes: list[list[tuple | None]] | None = None,
) -> Table | None:
    """Preserve ragged data for validation and flatten demonstrable merged headers."""
    rows = [[clean(c) for c in row] for row in raw]
    indices = [
        i
        for i, row in enumerate(rows)
        if any(row) and not FOOTER.fullmatch(" ".join(filter(None, row)))
    ]
    rows = [rows[i] for i in indices]
    if len(rows) < 2 or max(map(len, rows), default=0) < 2:
        return None
    width = max(map(len, rows))
    has_header = header_likely(rows[0], rows[1:])
    header_indices = []
    # Spanning top groups: pdfplumber represents merged cells as None/empty.
    if (
        len(rows) >= 3
        and sum(bool(c) for c in rows[0]) < width
        and sum(bool(c) for c in rows[1]) >= 2
        and all(kind(c) in {"text", "empty"} for c in rows[1])
        and any(kind(c) in {"numeric", "currency", "date", "id"} for row in rows[2:5] for c in row)
        and all(kind(c) in {"text", "empty"} for c in rows[0])
    ):
        parent = ""
        headers = []
        for c in range(width):
            parent = rows[0][c] or parent
            sub = rows[1][c] if c < len(rows[1]) else ""
            headers.append(" | ".join(filter(None, (parent, sub))))
        rows = rows[2:]
        header_indices, indices = indices[:2], indices[2:]
        has_header = True
    elif has_header:
        headers, rows = rows[0], rows[1:]
        header_indices, indices = indices[:1], indices[1:]
    else:
        headers = [f"Column {c + 1}" for c in range(width)]
    headers = [h or f"Column {c + 1}" for c, h in enumerate(headers)]
    table = Table(headers, rows, page, tuple(bbox), engine, confidence, has_header)
    if cell_boxes is not None:

        def source(r: int, c: int) -> list[dict]:
            if (
                len(header_indices) == 2
                and r == header_indices[0]
                and not raw[r][c]
                and raw[header_indices[1]][c]
            ):
                c = next((j for j in range(c - 1, -1, -1) if raw[r][j]), c)
            box = cell_boxes[r][c] if r < len(cell_boxes) and c < len(cell_boxes[r]) else None
            return [
                {
                    "page": page,
                    "bbox": list(box) if box else None,
                    "text": clean(raw[r][c]) if c < len(raw[r]) else "",
                    "engine": engine,
                    "confidence": None if engine.startswith("native") else confidence,
                    "coordinates": "page points",
                }
            ]

        table.cell_sources = [[source(r, c) for c in range(len(raw[r]))] for r in indices]
        table.header_sources = [
            [s for r in header_indices for s in source(r, c)] for c in range(len(headers))
        ]
    if not has_header:
        table.notes.append("Header uncertain; generic column labels used. First row retained.")
    return table


def words_to_grid(
    words: list[dict], page: int, engine: str, page_width: float, page_height: float
) -> list[Table]:
    """Infer recurring x anchors from word boxes, preserving empty cell positions."""
    from .layout import aligned_tables

    aligned = aligned_tables(words, page, engine)
    if aligned:
        return aligned
    if len(words) < 4:
        return []
    height = median(w["bottom"] - w["top"] for w in words)
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(median(w["top"] for w in lines[-1]) - word["top"]) < height * 0.55:
            lines[-1].append(word)
        else:
            lines.append([word])
    chunks = []
    for line in lines:
        parts: list[dict] = []
        for word in sorted(line, key=lambda w: w["x0"]):
            if parts and word["x0"] - parts[-1]["x1"] < max(4, height * 0.65):
                parts[-1]["text"] += " " + word["text"]
                parts[-1]["x1"] = word["x1"]
            else:
                parts.append(dict(word))
        if FOOTER.fullmatch(clean(" ".join(w["text"] for w in parts))):
            continue
        chunks.append(parts)
    candidates = [line for line in chunks if len(line) >= 2]
    if len(candidates) < 2:
        return []
    count = Counter(len(line) for line in candidates).most_common(1)[0][0]
    anchors = [
        median(
            sorted(line, key=lambda w: w["x0"])[c]["x0"]
            for line in candidates
            if len(line) == count
        )
        for c in range(count)
    ]
    rows, used, boxes = [], [], []
    # Learn the vertical data extent from dense aligned rows. Page titles and
    # footers with two distant text blocks must not become sparse table rows.
    dense = [line for line in chunks if len(line) >= max(2, count * 0.6)]
    top = min((min(w["top"] for w in line) for line in dense), default=0)
    bottom = max((max(w["bottom"] for w in line) for line in dense), default=page_height)
    for line in chunks:
        if not line:
            continue
        if (
            min(w["top"] for w in line) < top - height
            or max(w["bottom"] for w in line) > bottom + height * 2
        ):
            continue
        row = [""] * count
        row_words = [[] for _ in range(count)]
        for part in line:
            c = min(range(count), key=lambda i: abs(part["x0"] - anchors[i]))
            row[c] = clean(row[c] + " " + part["text"])
            row_words[c].append(part)
        if sum(bool(c) for c in row) < 2:
            continue
        rows.append(row)
        boxes.append(
            [
                (
                    min(w["x0"] for w in cell),
                    min(w["top"] for w in cell),
                    max(w["x1"] for w in cell),
                    max(w["bottom"] for w in cell),
                )
                if cell
                else None
                for cell in row_words
            ]
        )
        used.extend(line)
    if not used:
        return []
    bbox = (
        min(w["x0"] for w in used),
        min(w["top"] for w in used),
        max(w["x1"] for w in used),
        max(w["bottom"] for w in used),
    )
    table = normalize(rows, page, bbox, engine, 0.72, boxes)
    if table:
        table.notes.append("Columns inferred from word positions; review alignment.")
    return [table] if table else []
