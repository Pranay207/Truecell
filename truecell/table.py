"""Table normalization, conservative headers and word-box reconstruction."""
from __future__ import annotations

from collections import Counter
from statistics import median
import re

from .models import Table
from .values import kind

FOOTER = re.compile(r"^(?:page\s*)?\d+\s*(?:of|/)\s*\d+$|^page\s+\d+$", re.I)


def clean(value: object) -> str:
    """Normalize whitespace while preserving all non-whitespace characters."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def header_likely(first: list[str], following: list[list[str]]) -> bool:
    """Detect a textual header only when later contents provide evidence."""
    if not following:
        return False
    text = sum(kind(c) == "text" for c in first)
    if text < max(1, len(first) * .6):
        return False
    changes = sum(kind(first[c]) == "text" and any(
        c < len(row) and kind(row[c]) in {"numeric", "currency", "date", "id"}
        for row in following[:5]) for c in range(len(first)))
    return changes >= max(1, len(first) * .2)


def normalize(raw: list[list[object]], page: int, bbox: tuple,
              engine: str, confidence: float = 1.0) -> Table | None:
    """Preserve ragged data for validation and flatten demonstrable merged headers."""
    rows = [[clean(c) for c in row] for row in raw]
    rows = [row for row in rows if any(row) and not FOOTER.fullmatch(" ".join(filter(None, row)))]
    if len(rows) < 2 or max(map(len, rows), default=0) < 2:
        return None
    width = max(map(len, rows))
    has_header = header_likely(rows[0], rows[1:])
    # Spanning top groups: pdfplumber represents merged cells as None/empty.
    if (len(rows) >= 3 and sum(bool(c) for c in rows[0]) < width * .7
            and header_likely(rows[1], rows[2:])
            and all(kind(c) in {"text", "empty"} for c in rows[0])):
        parent = ""
        headers = []
        for c in range(width):
            parent = rows[0][c] or parent
            sub = rows[1][c] if c < len(rows[1]) else ""
            headers.append(" | ".join(filter(None, (parent, sub))))
        rows = rows[2:]
        has_header = True
    elif has_header:
        headers, rows = rows[0], rows[1:]
    else:
        headers = [f"Column {c + 1}" for c in range(width)]
    headers = [h or f"Column {c + 1}" for c, h in enumerate(headers)]
    table = Table(headers, rows, page, tuple(bbox), engine, confidence, has_header)
    if not has_header:
        table.notes.append("Header uncertain; generic column labels used. First row retained.")
    return table


def words_to_grid(words: list[dict], page: int, engine: str,
                  page_width: float, page_height: float) -> list[Table]:
    """Infer recurring x anchors from word boxes, preserving empty cell positions."""
    if len(words) < 4:
        return []
    height = median(w["bottom"] - w["top"] for w in words)
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(median(w["top"] for w in lines[-1]) - word["top"]) < height * .55:
            lines[-1].append(word)
        else:
            lines.append([word])
    chunks = []
    for line in lines:
        parts: list[dict] = []
        for word in sorted(line, key=lambda w: w["x0"]):
            if parts and word["x0"] - parts[-1]["x1"] < max(4, height * .65):
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
    anchors = [median(sorted(line, key=lambda w: w["x0"])[c]["x0"]
                      for line in candidates if len(line) == count) for c in range(count)]
    rows, used = [], []
    for line in chunks:
        if not line:
            continue
        row = [""] * count
        for part in line:
            c = min(range(count), key=lambda i: abs(part["x0"] - anchors[i]))
            row[c] = clean(row[c] + " " + part["text"])
        if sum(bool(c) for c in row) < 2:
            continue
        rows.append(row)
        used.extend(line)
    if not used:
        return []
    bbox = (min(w["x0"] for w in used), min(w["top"] for w in used),
            max(w["x1"] for w in used), max(w["bottom"] for w in used))
    table = normalize(rows, page, bbox, engine, .72)
    if table:
        table.notes.append("Columns inferred from word positions; review alignment.")
    return [table] if table else []
