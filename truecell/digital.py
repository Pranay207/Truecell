"""Native PDF extraction with independent ruled and borderless strategies."""

from __future__ import annotations

import pdfplumber

from .models import Table
from .table import normalize, words_to_grid


def extract_page(
    page: pdfplumber.page.Page, page_number: int, strategy: str = "lines"
) -> list[Table]:
    """Extract table regions rather than treating all page text as one table."""
    if strategy == "words":
        return words_to_grid(
            page.extract_words(), page_number, "native-words", page.width, page.height
        )
    settings = {
        "vertical_strategy": strategy,
        "horizontal_strategy": strategy,
        "intersection_tolerance": 5,
        "snap_tolerance": 3,
    }
    if strategy == "text":
        settings.update(
            min_words_vertical=3,
            min_words_horizontal=1,
            text_x_tolerance=2,
            text_y_tolerance=3,
        )
    tables = []
    for found in page.find_tables(settings):
        table = normalize(
            found.extract(x_tolerance=2, y_tolerance=3),
            page_number,
            found.bbox,
            f"native-{strategy}",
            0.98 if strategy == "lines" else 0.82,
            [row.cells for row in found.rows],
        )
        if table:
            if strategy == "text":
                table.notes.append("Borderless layout inferred; review column boundaries.")
            tables.append(table)
    return tables
