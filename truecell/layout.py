"""Reconstruct separated borderless tables from recurring numeric baselines.

Uses word positions and repeated column structure, never document filenames or
expected benchmark values. Ambiguous inferred layouts remain review findings.
"""

from __future__ import annotations

import re
from collections import Counter
from statistics import median

from .values import number


def aligned_tables(words: list[dict], page: int, engine: str) -> list:
    """Find stable table streams, preserve empty cells and flatten header paths."""
    from .table import normalize

    if len(words) < 10:
        return []
    height = median(w["bottom"] - w["top"] for w in words)
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - median(w["top"] for w in lines[-1])) < height * 0.55:
            lines[-1].append(word)
        else:
            lines.append([word])
    chunks = []
    for line in lines:
        parts = []
        for word in sorted(line, key=lambda w: w["x0"]):
            word = dict(word)
            original = word["text"]
            if re.fullmatch(r"[+-]?\d[\d,]*\s+\.\s*\d+", word["text"]):
                word["text"] = re.sub(r"\s+", "", word["text"])
            word["text"] = re.sub(r"(?:\s*\.\s*){3,}", "", word["text"]).strip()
            word["original_text"] = original
            # Dotted leaders are separators, not repeated data punctuation.
            if not word["text"] or re.fullmatch(r"\.+", word["text"]):
                continue
            if (
                parts
                and re.fullmatch(r"\.\d+", word["text"])
                and number(parts[-1]["text"]) is not None
                and word["x0"] - parts[-1]["x1"] < height * 0.7
            ):
                parts[-1]["text"] += word["text"]
                parts[-1]["original_text"] += " " + original
                parts[-1]["x1"] = word["x1"]
                continue
            if (
                parts
                and word["x0"] - parts[-1]["x1"] < max(3, height * 0.6)
                and not (number(parts[-1]["text"]) is not None and number(word["text"]) is not None)
            ):
                parts[-1]["text"] += " " + word["text"]
                parts[-1]["original_text"] += " " + original
                parts[-1]["x1"] = word["x1"]
            else:
                parts.append(dict(word))
        chunks.append(parts)
    seeds = [
        (i, line)
        for i, line in enumerate(chunks)
        if len(line) >= 3 and sum(number(w["text"]) is not None for w in line) >= 2
    ]
    if len(seeds) < 3:
        return []
    # A sustained change in table width establishes a new stream. Isolated
    # sparse rows do not split the table merely because one value is missing.
    runs = []
    run = []
    for j, item in enumerate(seeds):
        i, line = item
        dominant = Counter(len(p) for _, p in run).most_common(1)[0][0] if run else len(line)
        upcoming = seeds[j : j + 3]
        stable = len(upcoming) == 3 and all(abs(len(p) - len(line)) <= 1 for _, p in upcoming)
        if run and (
            abs(len(line) - dominant) >= 2
            and stable
            or line[0]["top"] - run[-1][1][0]["top"] > height * 8
        ):
            if len(run) >= 3:
                runs.append(run)
            run = []
        run.append(item)
    if len(run) >= 3:
        runs.append(run)
    output = []
    for group_index, group in enumerate(runs):
        count = Counter(len(line) for _, line in group).most_common(1)[0][0]
        complete = [line for _, line in group if len(line) == count]
        if len(complete) < 3:
            continue
        centers = [
            median((line[c]["x0"] + line[c]["x1"]) / 2 for line in complete) for c in range(count)
        ]
        if any(b - a < height * 0.8 for a, b in zip(centers, centers[1:])):
            continue

        def column(word):
            center = (word["x0"] + word["x1"]) / 2
            return min(range(count), key=lambda c: abs(center - centers[c]))

        first, last = group[0][0], group[-1][0]
        data_top = min(w["top"] for w in chunks[first])
        lower = data_top - height * 9
        if group_index:
            lower = max(lower, max(w["bottom"] for w in runs[group_index - 1][-1][1]) + height)
        prefix = [
            line
            for i, line in enumerate(chunks[:first])
            if line and min(w["top"] for w in line) >= lower
        ]
        # Ignore single prose/title blocks. Text spanning the numeric columns
        # with at least two separated anchors can establish header context.
        prefix = [
            line
            for line in prefix
            if (
                len(line) >= 2
                or len(line) == 1
                and line[0]["x1"] - line[0]["x0"]
                <= median(b - a for a, b in zip(centers, centers[1:])) * 2
            )
            and sum(number(w["text"]) is not None for w in line) < 2
        ]
        headers = [""] * count
        header_words = [[] for _ in range(count)]
        for li, line in enumerate(prefix):
            parent_line = (
                li == 0
                and 2 <= len(line) < count * 0.6
                and len(prefix) > 1
                and max(w["x1"] for w in line) - min(w["x0"] for w in line)
                > (centers[-1] - centers[1]) * 0.55
            )
            if parent_line:
                owners = Counter(
                    min(
                        range(len(line)),
                        key=lambda i: abs((line[i]["x0"] + line[i]["x1"]) / 2 - centers[c]),
                    )
                    for c in range(1, count)
                )
                parent_line = sum(n >= 2 for n in owners.values()) >= 2
            for word in line:
                if parent_line:
                    # Parent centers divide the child columns horizontally.
                    eligible = (
                        range(1, count) if word["x0"] > centers[0] + height * 2 else range(count)
                    )
                    for c in eligible:
                        owner = min(line, key=lambda p: abs((p["x0"] + p["x1"]) / 2 - centers[c]))
                        if owner is word:
                            header_words[c].append({**word, "parent": True})
                else:
                    header_words[column(word)].append(word)
        has_header = any(header_words) and sum(bool(cell) for cell in header_words) >= count * 0.6
        if has_header:
            for c, cell in enumerate(header_words):
                parents = " ".join(w["text"] for w in cell if w.get("parent"))
                children = " ".join(w["text"] for w in cell if not w.get("parent"))
                headers[c] = " | ".join(v for v in [parents, children] if v) or f"Column {c + 1}"
        rows = []
        boxes = []
        row_words = []
        baselines = []
        for i, line in group:
            if abs(len(line) - count) > 1:
                continue
            cells = [[] for _ in range(count)]
            for word in line:
                cells[column(word)].append(word)
            row_words.append(cells)
            baselines.append(median(w["top"] for w in line))
        seed_indices = {i for i, _ in group}
        from .validate import total_row

        step = (
            median(b - a for a, b in zip(baselines, baselines[1:]))
            if len(baselines) > 1
            else height * 3
        )
        end = last
        for i in range(last + 1, len(chunks)):
            if not chunks[i]:
                continue
            if min(w["top"] for w in chunks[i]) - baselines[-1] > step * 1.8:
                break
            if total_row([w["text"] for w in chunks[i]]):
                end = i
        for i in range(first, end + 1):
            if i in seed_indices or not chunks[i]:
                continue
            line = chunks[i]
            if sum(number(w["text"]) is not None for w in line) >= 2:
                continue
            baseline = median(w["top"] for w in line)
            r = min(range(len(baselines)), key=lambda r: abs(baselines[r] - baseline))
            columns = {column(w) for w in line}
            if (
                total_row([w["text"] for w in line])
                or 0 in columns
                and len(columns) >= 2
                and abs(baselines[r] - baseline) > height * 0.75
            ):
                cells = [[] for _ in range(count)]
                for word in line:
                    cells[column(word)].append(word)
                row_words.append(cells)
                baselines.append(baseline)
                continue
            # A label-only line above a numeric row commonly belongs to that
            # row's wrapped first column, rather than the preceding record.
            if len(line) == 1 and column(line[0]) == 0:
                following = [j for j, y in enumerate(baselines) if 0 < y - baseline <= height * 2]
                if following:
                    r = min(following, key=lambda j: baselines[j])
            if abs(baselines[r] - baseline) <= height * 1.6:
                for word in line:
                    row_words[r][column(word)].append(word)

        def text(cell):
            return " ".join(
                w["text"]
                for w in sorted(
                    cell, key=lambda w: (round(w["top"] / max(1, height * 0.6)), w["x0"])
                )
            )

        def box(cell):
            return (
                (
                    min(w["x0"] for w in cell),
                    min(w["top"] for w in cell),
                    max(w["x1"] for w in cell),
                    max(w["bottom"] for w in cell),
                )
                if cell
                else None
            )

        row_words = [
            row_words[i] for i in sorted(range(len(row_words)), key=lambda i: baselines[i])
        ]
        for cells in row_words:
            rows.append([text(cell) for cell in cells])
            boxes.append([box(cell) for cell in cells])
        used = [w for row in row_words for cell in row for w in cell]
        if not used:
            continue
        bbox = (
            min(w["x0"] for w in used),
            min(w["top"] for w in used),
            max(w["x1"] for w in used),
            max(w["bottom"] for w in used),
        )
        raw = ([headers] if has_header else []) + rows
        all_boxes = ([[box(cell) for cell in header_words]] if has_header else []) + boxes
        table = normalize(raw, page, bbox, engine, 0.78, all_boxes)
        if table:
            table.notes.append(
                "Borderless columns and header paths inferred from repeated word positions; verify source alignment."
            )
            for r, cells in enumerate(row_words):
                for c, cell in enumerate(cells):
                    original = " ".join(
                        w.get("original_text", w["text"])
                        for w in sorted(cell, key=lambda w: (w["top"], w["x0"]))
                    )
                    for record in table.cell_sources[r][c]:
                        record["initial_reading"] = original
            output.append(table)
    return output
