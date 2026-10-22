"""Table normalization, conservative headers and word-box reconstruction."""

from __future__ import annotations

import re
from collections import Counter
from statistics import median

from .models import Table
from .values import kind

FOOTER = re.compile(r"^(?:page\s*)?\d+\s*(?:of|/)\s*\d+$|^page\s+\d+$", re.I)
TITLE_WORDS = re.compile(
    r"\b(?:report|register|statement|schedule|list|invoice|summary|directory|roster|ledger)\b",
    re.I,
)
VERTICAL_MERGE_NOTE = (
    "Vertically merged group labels repeated into child rows from explicit ruled "
    "geometry; inherited cells reuse the original source box."
)
NESTED_GROUP_NOTE = (
    "Explicit body group labels retained as nested section rows; no child values were imputed."
)
HORIZONTAL_MERGE_NOTE = (
    "Merged body labels retained in their source cell with covered cells blank; no values were "
    "imputed across columns."
)
MULTILEVEL_HEADER_NOTE = "Multi-level merged headers flattened into source-backed column paths."
UNRULED_VERTICAL_NOTE = (
    "Possible unruled vertical group spans remain blank because the available geometry does not "
    "prove inheritance; review those cells against the source."
)

GROUP_HEADER = re.compile(
    r"\b(?:group|section|category|package|phase|department|division|class|part|chapter|"
    r"work\s*package|lot)\b",
    re.I,
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


def _title_row_likely(
    rows: list[list[str]],
    width: int,
    cell_boxes: list[list[tuple | None]] | None,
    raw_index: int,
    table_bbox: tuple,
) -> bool:
    """Separate a document title from a real spanning parent header.

    A single spanning label such as ``Movement`` can be a legitimate parent
    header, so title removal requires both a complete leaf-header row below it
    and title-like text or strong full-width geometry.  The row is retained as
    page evidence rather than being discarded silently.
    """
    if len(rows) < 3 or width < 3:
        return False
    occupied = [clean(value) for value in rows[0] if clean(value)]
    dense_leaf = (
        sum(bool(clean(value)) for value in rows[1]) >= width * 0.6
        and all(kind(value) in {"text", "empty"} for value in rows[1])
        and sum(sum(bool(clean(value)) for value in row) >= width * 0.6 for row in rows[2:5])
        >= min(2, len(rows[2:5]))
    )
    if len(occupied) != 1 or not (header_likely(rows[1], rows[2:]) or dense_leaf):
        return False
    title = occupied[0]
    # Short labels such as ``SECTION A`` or ``Work package 1`` can be a real
    # parent header spanning every column.  A longer full-width caption that
    # happens to contain one of those words (for example a page-specific
    # ``... - section 10`` title) is document context when a complete leaf
    # header follows it.  Keeping the exemption deliberately concise avoids
    # copying a page caption into every column while preserving ordinary group
    # headers.
    group_tokens = re.findall(r"[\w]+", title, flags=re.UNICODE)
    concise_group_label = len(group_tokens) <= 3
    if _strong_group_label(title) and not TITLE_WORDS.search(title) and concise_group_label:
        return False
    letters = "".join(character for character in title if character.isalpha())
    lexical = bool(TITLE_WORDS.search(title)) or (
        len(title.split()) >= 2 and bool(letters) and letters.upper() == letters
    )
    full_width = False
    if cell_boxes is not None and raw_index < len(cell_boxes):
        boxes = [box for box in cell_boxes[raw_index] if box is not None and len(box) >= 4]
        table_width = max(1.0, float(table_bbox[2]) - float(table_bbox[0]))
        full_width = bool(boxes) and max(box[2] - box[0] for box in boxes) / table_width >= 0.82
    # Geometry alone is accepted only for a multi-word title; this preserves
    # one-word full-width group headers such as "Product" or "Movement".
    return lexical or full_width and len(title.split()) >= 2


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
            (top, bottom) for top, bottom in intervals if bottom - top <= shortest + tolerance
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
                if source_box[1] <= row_top + tolerance and source_box[3] >= row_bottom - tolerance:
                    origins[(raw_index, column)] = source_index
                break
    return origins


def _box_at(cell_boxes: list[list[tuple | None]] | None, row: int, column: int) -> tuple | None:
    if cell_boxes is None or row >= len(cell_boxes) or column >= len(cell_boxes[row]):
        return None
    box = cell_boxes[row][column]
    return box if box is not None and len(box) >= 4 else None


def _header_token(value: str) -> bool:
    """Return whether a scalar can safely label a header level."""
    text = clean(value)
    return bool(
        not text
        or kind(text) == "text"
        or re.fullmatch(r"(?:19|20)\d{2}", text)
        or re.fullmatch(r"(?:q[1-4]|h[12]|fy\s*\d{2,4})", text, re.I)
    )


def _parent_header_geometry(
    raw_index: int,
    values: list[str],
    width: int,
    cell_boxes: list[list[tuple | None]] | None,
    table_bbox: tuple,
) -> bool:
    """Return whether a level is clearly a parent rather than a merged leaf header.

    A single wide cell in an otherwise dense leaf row is not enough to justify
    consuming the next all-text row as another header axis.  Parent levels are
    sparse or contain multiple independent horizontal spans.
    """
    if cell_boxes is None or raw_index >= len(cell_boxes):
        return False
    table_width = max(1.0, float(table_bbox[2]) - float(table_bbox[0]))
    nominal_width = table_width / max(1, width)
    spanning = sum(
        box is not None and len(box) >= 4 and float(box[2]) - float(box[0]) > nominal_width * 1.45
        for box in cell_boxes[raw_index]
    )
    populated = sum(bool(clean(value)) for value in values)
    return spanning >= 2 or spanning == 1 and populated <= max(1, width // 2)


def _header_depth(
    rows: list[list[str]],
    width: int,
    cell_boxes: list[list[tuple | None]] | None,
    raw_indices: list[int],
    table_bbox: tuple,
) -> int:
    """Find a conservative two-to-four-row merged header hierarchy."""
    if len(rows) < 3:
        return 0
    first_values = [(column, clean(value)) for column, value in enumerate(rows[0]) if clean(value)]
    if len(first_values) == 1 and _strong_group_label(first_values[0][1]):
        first_box = _box_at(cell_boxes, raw_indices[0], first_values[0][0])
        table_width = max(1.0, float(table_bbox[2]) - float(table_bbox[0]))
        full_width_parent = (
            first_box is not None
            and (float(first_box[2]) - float(first_box[0])) / table_width >= 0.8
        )
        if not full_width_parent:
            return 0
    first_sparse = sum(bool(c) for c in rows[0]) < width
    later_data = any(
        kind(c) in {"numeric", "currency", "date", "id"} for row in rows[2:6] for c in row
    )
    if not first_sparse or not later_data or not all(_header_token(c) for c in rows[0]):
        return 0
    depth = 1
    for position in range(1, min(4, len(rows) - 1)):
        row = rows[position]
        following = rows[position + 1 : position + 5]
        dense = sum(bool(c) for c in row) >= max(2, width * 0.3)
        header_evidence = header_likely(row, following)
        if all(_header_token(c) for c in row) and (dense or header_evidence):
            depth += 1
            # Continue only when this accepted level is affirmatively a parent
            # level. A dense leaf row with one merged label must end the header;
            # otherwise an all-text first data row can be silently consumed.
            if not _parent_header_geometry(
                raw_indices[position], row, width, cell_boxes, table_bbox
            ):
                break
            continue
        break
    return depth if depth >= 2 else 0


def _header_paths(
    raw: list[list[object]],
    header_indices: list[int],
    width: int,
    cell_boxes: list[list[tuple | None]] | None,
    table_bbox: tuple,
) -> tuple[list[str], list[list[int | None]]]:
    """Flatten merged header levels and retain the source cell for every path part."""
    table_left, table_right = float(table_bbox[0]), float(table_bbox[2])
    step = max(1.0, table_right - table_left) / width
    centers = [table_left + (column + 0.5) * step for column in range(width)]
    # Dense body/header cells give better column centers than equal-width fallback.
    for column in range(width):
        candidates = []
        for row, boxes in enumerate(cell_boxes or []):
            if column >= len(boxes):
                continue
            box = _box_at(cell_boxes, row, column)
            if box is not None and (box[2] - box[0]) <= step * 1.6:
                candidates.append((box[0] + box[2]) / 2)
        if candidates:
            centers[column] = median(candidates)

    levels: list[list[str]] = []
    owners: list[list[int | None]] = []
    for raw_index in header_indices:
        values = [clean(raw[raw_index][c]) if c < len(raw[raw_index]) else "" for c in range(width)]
        level = [""] * width
        owner_row: list[int | None] = [None] * width
        populated = [c for c, value in enumerate(values) if value]
        for source_column in populated:
            value = values[source_column]
            box = _box_at(cell_boxes, raw_index, source_column)
            covered = (
                [c for c, center in enumerate(centers) if box[0] - 0.75 <= center <= box[2] + 0.75]
                if box is not None
                else []
            )
            if not covered:
                next_column = next((c for c in populated if c > source_column), width)
                covered = list(range(source_column, next_column))
            for column in covered:
                # Do not let a coarse parent overwrite an explicit cell at this level.
                if not level[column] or column == source_column:
                    level[column] = value
                    owner_row[column] = source_column
        levels.append(level)
        owners.append(owner_row)

    headers = []
    for column in range(width):
        path = []
        for level in levels:
            value = level[column]
            if value and (not path or value.casefold() != path[-1].casefold()):
                path.append(value)
        headers.append(" | ".join(path) or f"Column {column + 1}")
    return headers, owners


def _strong_group_label(value: str) -> bool:
    text = clean(value)
    letters = "".join(character for character in text if character.isalpha())
    return bool(
        text
        and kind(text) == "text"
        and (
            GROUP_HEADER.search(text)
            or text.endswith(":")
            or len(text.split()) >= 2
            and len(letters) >= 4
            and letters.upper() == letters
        )
    )


def _structural_annotations(
    raw: list[list[object]],
    indices: list[int],
    width: int,
    bbox: tuple,
    cell_boxes: list[list[tuple | None]] | None,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Identify explicit horizontal spans and conservative nested group rows."""
    horizontal: set[tuple[int, int]] = set()
    nested: set[tuple[int, int]] = set()
    table_width = max(1.0, float(bbox[2]) - float(bbox[0]))
    nominal_width = table_width / max(1, width)
    for raw_index in indices:
        populated = [c for c, value in enumerate(raw[raw_index]) if clean(value)]
        for column in populated:
            value = clean(raw[raw_index][column])
            box = _box_at(cell_boxes, raw_index, column)
            if box is not None and kind(value) == "text" and box[2] - box[0] >= nominal_width * 1.6:
                horizontal.add((raw_index, column))
        if len(populated) != 1:
            continue
        column = populated[0]
        value = clean(raw[raw_index][column])
        box = _box_at(cell_boxes, raw_index, column)
        full_width = box is not None and (box[2] - box[0]) / table_width >= 0.8
        if kind(value) == "text" and (full_width or _strong_group_label(value)):
            nested.add((raw_index, column))
    return horizontal, nested


def _possible_unruled_vertical_spans(
    headers: list[str], rows: list[list[str]], engine: str
) -> bool:
    """Detect ambiguous hierarchy blanks, deliberately without filling them."""
    if engine.endswith("-lines"):
        return False
    for column, header in enumerate(headers[:-1]):
        if not GROUP_HEADER.search(header):
            continue
        prior = ""
        for row in rows:
            value = clean(row[column]) if column < len(row) else ""
            if value:
                prior = value
            elif prior and sum(bool(clean(cell)) for cell in row) >= 2:
                return True
    return False


def annotate_unruled_structure(table: Table) -> None:
    """Label explicit section rows and disclose unresolved vertical spans."""
    nested = False
    table_width = max(1.0, table.bbox[2] - table.bbox[0])
    for row_index, row in enumerate(table.rows):
        populated = [column for column, value in enumerate(row) if clean(value)]
        if len(populated) != 1:
            continue
        column = populated[0]
        sources = table.cell_sources[row_index][column]
        boxes = [source.get("bbox") for source in sources if source.get("bbox")]
        full_width = bool(boxes) and max(box[2] - box[0] for box in boxes) / table_width >= 0.8
        if full_width or _strong_group_label(row[column]):
            nested = True
            for source in sources:
                source["role"] = "nested_group_label"
    if nested and NESTED_GROUP_NOTE not in table.notes:
        table.notes.append(NESTED_GROUP_NOTE)
    if (
        _possible_unruled_vertical_spans(table.headers, table.rows, table.engine)
        and UNRULED_VERTICAL_NOTE not in table.notes
    ):
        table.notes.append(UNRULED_VERTICAL_NOTE)


def normalize(
    raw: list[list[object]],
    page: int,
    bbox: tuple,
    engine: str,
    confidence: float = 1.0,
    cell_boxes: list[list[tuple | None]] | None = None,
    row_indices: list[int] | None = None,
    ruled_geometry: bool | None = None,
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
    title_index: int | None = None
    if _title_row_likely(rows, width, cell_boxes, indices[0], bbox):
        title_index = indices[0]
        rows = rows[1:]
        indices = indices[1:]
    has_header = title_index is not None or header_likely(rows[0], rows[1:])
    header_indices: list[int] = []
    header_owners: list[list[int | None]] = []
    # pdfplumber and OCR topology represent merged cells with one source cell
    # followed by empty covered positions. Support two to four header axes.
    header_depth = _header_depth(rows, width, cell_boxes, indices, bbox)
    if header_depth:
        header_indices, indices = indices[:header_depth], indices[header_depth:]
        headers, header_owners = _header_paths(raw, header_indices, width, cell_boxes, bbox)
        rows = rows[header_depth:]
        has_header = True
    elif has_header:
        headers, rows = rows[0] + [""] * (width - len(rows[0])), rows[1:]
        header_indices, indices = indices[:1], indices[1:]
    else:
        headers = [f"Column {c + 1}" for c in range(width)]
    headers = [h or f"Column {c + 1}" for c, h in enumerate(headers)]
    vertical_origins: dict[tuple[int, int], int] = {}
    horizontal_spans: set[tuple[int, int]] = set()
    nested_groups: set[tuple[int, int]] = set()
    if cell_boxes is not None:
        supports_ruled_spans = (
            engine == "native-lines" if ruled_geometry is None else ruled_geometry
        )
        if supports_ruled_spans:
            vertical_origins = _vertical_merge_origins(raw, cell_boxes, indices)
        for data_row, raw_index in enumerate(indices):
            for column in range(len(rows[data_row])):
                source_index = vertical_origins.get((raw_index, column))
                if source_index is not None:
                    rows[data_row][column] = clean(raw[source_index][column])
        horizontal_spans, nested_groups = _structural_annotations(
            raw, indices, width, bbox, cell_boxes
        )
        if not supports_ruled_spans:
            horizontal_spans.clear()
    table = Table(headers, rows, page, tuple(bbox), engine, confidence, has_header)
    if title_index is not None:
        title_cell = next(
            (c for c, value in enumerate(raw[title_index]) if clean(value)),
            0,
        )
        title_box = (
            cell_boxes[title_index][title_cell]
            if cell_boxes is not None
            and title_index < len(cell_boxes)
            and title_cell < len(cell_boxes[title_index])
            else None
        )
        title = clean(raw[title_index][title_cell])
        table.page_summaries.append(
            {
                "page": page,
                "text": title,
                "bbox": list(title_box) if title_box else None,
                "role": "document_title",
            }
        )
    if vertical_origins:
        table.notes.append(VERTICAL_MERGE_NOTE)
    if nested_groups:
        table.notes.append(NESTED_GROUP_NOTE)
    if horizontal_spans - nested_groups:
        table.notes.append(HORIZONTAL_MERGE_NOTE)
    if len(header_indices) > 1:
        table.notes.append(MULTILEVEL_HEADER_NOTE)
    if _possible_unruled_vertical_spans(headers, rows, engine):
        table.notes.append(UNRULED_VERTICAL_NOTE)
    if row_indices is not None:
        row_indices.extend(indices)
    if cell_boxes is not None:

        def source(r: int, c: int) -> list[dict]:
            inherited = (r, c) in vertical_origins
            nested_group = (r, c) in nested_groups
            horizontal_span = (r, c) in horizontal_spans
            if inherited:
                r = vertical_origins[(r, c)]
            source_row, source_column = r, c
            box = cell_boxes[r][c] if r < len(cell_boxes) and c < len(cell_boxes[r]) else None
            return [
                {
                    "page": page,
                    "bbox": list(box) if box else None,
                    "text": clean(raw[r][c]) if c < len(raw[r]) else "",
                    "engine": engine,
                    "confidence": None if engine.startswith("native") else confidence,
                    "coordinates": "page points",
                    "source_row": source_row + 1,
                    "source_column": source_column + 1,
                    **(
                        {"role": "vertical_merge_expansion"}
                        if inherited
                        else {"role": "nested_group_label"}
                        if nested_group
                        else {"role": "horizontal_merge_label"}
                        if horizontal_span
                        else {}
                    ),
                }
            ]

        table.cell_sources = [[source(r, c) for c in range(len(raw[r]))] for r in indices]
        if header_owners:
            table.header_sources = []
            for column in range(len(headers)):
                records = []
                for level, raw_index in enumerate(header_indices):
                    owner = header_owners[level][column]
                    if owner is None:
                        continue
                    for record in source(raw_index, owner):
                        record["role"] = "merged_header_path"
                        if not records or (record["text"], record["bbox"]) != (
                            records[-1]["text"],
                            records[-1]["bbox"],
                        ):
                            records.append(record)
                table.header_sources.append(records)
        else:
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
