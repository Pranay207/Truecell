"""Table normalization, conservative headers and word-box reconstruction."""

from __future__ import annotations

import re
from collections import Counter
from statistics import median

from .models import Table
from .values import kind

FOOTER = re.compile(r"^(?:page\s*)?\d+\s*(?:of|/)\s*\d+$|^page\s+\d+$", re.I)
VERTICAL_MERGE_NOTE = (
    "Vertically merged group labels repeated into child rows from explicit ruled "
    "geometry; inherited cells reuse the original source box."
)


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


def _vertical_merge_origins(
    raw: list[list[object]],
    cell_boxes: list[list[tuple | None]],
    data_indices: list[int],
) -> dict[tuple[int, int], int]:
    """Map blank child cells to a prior cell only when its box spans that row."""
    origins: dict[tuple[int, int], int] = {}
    tolerance = 0.75
    for position, raw_index in enumerate(data_indices):
        if raw_index >= len(cell_boxes):
            continue
        current_boxes = cell_boxes[raw_index]
        intervals = [
            (box[1], box[3])
            for box in current_boxes
            if box is not None and len(box) >= 4 and box[3] > box[1]
        ]
        # A row needs independent cells to establish its actual vertical band.
        if len(intervals) < 2:
            continue
        shortest = min(bottom - top for top, bottom in intervals)
        row_intervals = [
            (top, bottom)
            for top, bottom in intervals
            if bottom - top <= shortest + tolerance
        ]
        row_top = median(top for top, _ in row_intervals)
        row_bottom = median(bottom for _, bottom in row_intervals)
        if row_bottom <= row_top:
            continue
        for column in range(len(raw[raw_index])):
            current_box = current_boxes[column] if column < len(current_boxes) else None
            if clean(raw[raw_index][column]) or current_box is not None:
                continue
            for source_index in reversed(data_indices[:position]):
                source_row = raw[source_index]
                source_boxes = cell_boxes[source_index] if source_index < len(cell_boxes) else []
                source_box = source_boxes[column] if column < len(source_boxes) else None
                source_value = clean(source_row[column]) if column < len(source_row) else ""
                # An explicit intervening cell, even if empty, ends the earlier span.
                if source_box is not None and not source_value:
                    break
                if not source_value:
                    continue
                if source_box is None or len(source_box) < 4:
                    break
                if kind(source_value) not in {"text", "id", "date"}:
                    break
                if (
                    source_box[1] <= row_top + tolerance
                    and source_box[3] >= row_bottom - tolerance
                ):
                    origins[(raw_index, column)] = source_index
                break
    return origins


def normalize(
    raw: list[list[object]],
    page: int,
    bbox: tuple,
    engine: str,
    confidence: float = 1.0,
    cell_boxes: list[list[tuple | None]] | None = None,
    row_indices: list[int] | None = None,
) -> Table | None:
    """Normalize tables; optionally return raw data-row indexes for OCR evidence."""
    if row_indices is not None:
        row_indices.clear()
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
            top = rows[0][c] if c < len(rows[0]) else ""
            parent = top or parent
            sub = rows[1][c] if c < len(rows[1]) else ""
            headers.append(" | ".join(filter(None, (parent, sub))))
        rows = rows[2:]
        header_indices, indices = indices[:2], indices[2:]
        has_header = True
    elif has_header:
        headers, rows = rows[0] + [""] * (width - len(rows[0])), rows[1:]
        header_indices, indices = indices[:1], indices[1:]
    else:
        headers = [f"Column {c + 1}" for c in range(width)]
    headers = [h or f"Column {c + 1}" for c, h in enumerate(headers)]
    vertical_origins: dict[tuple[int, int], int] = {}
    if engine == "native-lines" and cell_boxes is not None:
        vertical_origins = _vertical_merge_origins(raw, cell_boxes, indices)
        for data_row, raw_index in enumerate(indices):
            for column in range(len(rows[data_row])):
                source_index = vertical_origins.get((raw_index, column))
                if source_index is not None:
                    rows[data_row][column] = clean(raw[source_index][column])
    table = Table(headers, rows, page, tuple(bbox), engine, confidence, has_header)
    if vertical_origins:
        table.notes.append(VERTICAL_MERGE_NOTE)
    if row_indices is not None:
        row_indices.extend(indices)
    if cell_boxes is not None:

        def source(r: int, c: int) -> list[dict]:
            inherited = (r, c) in vertical_origins
            if inherited:
                r = vertical_origins[(r, c)]
            top_value = raw[r][c] if c < len(raw[r]) else None
            second_value = (
                raw[header_indices[1]][c]
                if len(header_indices) == 2
                and c < len(raw[header_indices[1]])
                else None
            )
            if (
                len(header_indices) == 2
                and r == header_indices[0]
                and not top_value
                and second_value
            ):
                c = next(
                    (j for j in range(c - 1, -1, -1) if j < len(raw[r]) and raw[r][j]),
                    c,
                )
            box = cell_boxes[r][c] if r < len(cell_boxes) and c < len(cell_boxes[r]) else None
            return [
                {
                    "page": page,
                    "bbox": list(box) if box else None,
                    "text": clean(raw[r][c]) if c < len(raw[r]) else "",
                    "engine": engine,
                    "confidence": None if engine.startswith("native") else confidence,
                    "coordinates": "page points",
                    **({"role": "vertical_merge_expansion"} if inherited else {}),
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
    if not any(kind(w["text"]) in {"numeric", "currency", "date", "id"} for w in words):
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
