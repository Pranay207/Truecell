"""Generate a disclosed 13-page challenge-equivalent development fixture.

This is dummy data.  It is not the private document referenced by the external
review and must never be described as that document.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
PAGE_WIDTH, PAGE_HEIGHT = 1580, 900
ROW_HEIGHT = 50
TITLE_HEIGHT = 28
HEADER_HEIGHT = 44
WIDTHS = [70, 105, 145, 105, 110, 105, 120, 95, 80, 85, 80, 80, 105, 155]


SCHEMAS = [
    (
        "Personnel register",
        [
            "S No",
            "Employee ID",
            "Full Name",
            "Role",
            "Unit",
            "District",
            "Phone",
            "Join Date",
            "Grade",
            "Shift",
            "Active",
            "Cases",
            "Hours",
            "Remarks",
        ],
    ),
    (
        "Equipment issue register",
        [
            "Issue ID",
            "Issue Date",
            "Station",
            "Item Code",
            "Item Description",
            "Category",
            "Quantity",
            "Unit Cost",
            "Total",
            "Custodian",
            "Phone",
            "Status",
            "Return Date",
            "Notes",
        ],
    ),
    (
        "Incident summary",
        [
            "Report ID",
            "Date",
            "Time",
            "Location",
            "Category",
            "Officer ID",
            "Officer Name",
            "People",
            "Vehicles",
            "Property",
            "Status",
            "Reviewer",
            "District",
            "Notes",
        ],
    ),
    (
        "Training attendance",
        [
            "Batch",
            "Date",
            "Course",
            "Employee ID",
            "Participant Name",
            "Unit",
            "Role",
            "Session",
            "Hours",
            "Score",
            "Result",
            "Trainer",
            "Location",
            "Notes",
        ],
    ),
]


def rows_for(table: int, count: int) -> list[list[str]]:
    rows = []
    for index in range(count):
        number = index + 1
        phone = f"9{table}{number:08d}"
        date = f"2026-{table + 1:02d}-{number % 28 + 1:02d}"
        if table == 0:
            rows.append(
                [
                    str(number),
                    f"00{table + 1}{number:04d}",
                    f"Officer Sample Name {number}",
                    ["Inspector", "Constable", "Analyst"][index % 3],
                    f"Unit {index % 5 + 1}",
                    ["North", "South", "East", "West"][index % 4],
                    phone,
                    date,
                    str(index % 6 + 1),
                    str(index % 3 + 1),
                    str(index % 2),
                    str(index % 8),
                    f"{8 + index % 4}.00",
                    "Routine roster entry",
                ]
            )
        elif table == 1:
            qty, cost = index % 5 + 1, 25 + index % 9
            rows.append(
                [
                    f"IS-{number:04d}",
                    date,
                    f"Station {index % 6 + 1}",
                    f"IT-{number:04d}",
                    f"Protective equipment set {number}",
                    "Equipment",
                    str(qty),
                    f"{cost:.2f}",
                    f"{qty * cost:.2f}",
                    f"Officer {number}",
                    phone,
                    ["Issued", "Returned"][index % 2],
                    f"2026-12-{number % 28 + 1:02d}",
                    "Checked before issue",
                ]
            )
        elif table == 2:
            rows.append(
                [
                    f"RP-{number:04d}",
                    date,
                    f"{8 + index % 12:02d}:30",
                    f"Sector {index % 7 + 1}",
                    ["Traffic", "Service", "Patrol"][index % 3],
                    f"00{table + 1}{number:04d}",
                    f"Officer Review Name {number}",
                    str(index % 6),
                    str(index % 4),
                    f"{index * 10}.00",
                    ["Open", "Closed", "Review"][index % 3],
                    f"Reviewer {index % 5 + 1}",
                    ["North", "South", "Central"][index % 3],
                    "Source checked entry",
                ]
            )
        else:
            rows.append(
                [
                    f"BT-{number:04d}",
                    date,
                    f"Operational safety course {index % 4 + 1}",
                    f"00{table + 1}{number:04d}",
                    f"Participant Sample Name {number}",
                    f"Unit {index % 5 + 1}",
                    ["Officer", "Supervisor", "Analyst"][index % 3],
                    str(index % 3 + 1),
                    f"{4 + index % 5}.00",
                    str(60 + index % 41),
                    "Pass" if index % 7 else "Review",
                    f"Trainer {index % 4 + 1}",
                    f"Centre {index % 3 + 1}",
                    "Attendance verified",
                ]
            )
    return rows


def draw_cell_text(pdf, value: str, x: float, y: float, width: float, height: float) -> None:
    words = str(value).split()
    if len(value) > 18 and len(words) > 1:
        midpoint = max(1, len(words) // 2)
        lines = (" ".join(words[:midpoint]), " ".join(words[midpoint:]))
    else:
        lines = (str(value),)
    pdf.setFont("Helvetica", 7.3)
    for line_index, line in enumerate(lines[:2]):
        clipped = (
            line
            if len(line) <= max(4, int(width / 4.4))
            else line[: max(3, int(width / 4.4) - 3)] + "..."
        )
        pdf.drawString(x + 3, y + height - 16 - line_index * 12, clipped)


def draw_page(pdf, title: str, headers: list[str], rows: list[list[str]], page: int) -> None:
    x, top = 25, 820
    table_width = sum(WIDTHS)
    pdf.setStrokeColor(HexColor("#81909d"))
    pdf.setLineWidth(0.55)
    # One full-width document title row. It is context, not a parent header.
    pdf.rect(x, top - TITLE_HEIGHT, table_width, TITLE_HEIGHT)
    pdf.setFillColor(HexColor("#15344a"))
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(x + 6, top - 19, f"Dummy {title} - section {page}")

    header_top = top - TITLE_HEIGHT
    pdf.setFillColor(HexColor("#e8f1ef"))
    pdf.rect(x, header_top - HEADER_HEIGHT, table_width, HEADER_HEIGHT, fill=1, stroke=1)
    offset = x
    for width, header in zip(WIDTHS, headers):
        pdf.line(offset, header_top, offset, header_top - HEADER_HEIGHT)
        pdf.setFillColor(HexColor("#15344a"))
        draw_cell_text(pdf, header, offset, header_top - HEADER_HEIGHT, width, HEADER_HEIGHT)
        offset += width
    pdf.line(x + table_width, header_top, x + table_width, header_top - HEADER_HEIGHT)

    data_top = header_top - HEADER_HEIGHT
    for row_index, row in enumerate(rows):
        y = data_top - (row_index + 1) * ROW_HEIGHT
        offset = x
        for width, value in zip(WIDTHS, row):
            pdf.rect(offset, y, width, ROW_HEIGHT)
            pdf.setFillColor(HexColor("#172d3d"))
            draw_cell_text(pdf, value, offset, y, width, ROW_HEIGHT)
            offset += width
    pdf.setFillColor(HexColor("#172d3d"))
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(PAGE_WIDTH - 25, 24, f"Page {page} of 13")


def write_fixture(directory: Path) -> None:
    name = "G_thirteen_page_equivalent"
    directory.mkdir(parents=True, exist_ok=True)
    page_counts = [3, 3, 3, 4]
    rows_per_page = 6
    tables = []
    pdf = canvas.Canvas(
        str(directory / f"{name}.pdf"),
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        invariant=1,
    )
    absolute_page = 1
    for table_index, ((title, headers), pages) in enumerate(zip(SCHEMAS, page_counts)):
        rows = rows_for(table_index, pages * rows_per_page)
        tables.append({"headers": headers, "rows": rows})
        for local_page in range(pages):
            start = local_page * rows_per_page
            draw_page(
                pdf,
                title,
                headers,
                rows[start : start + rows_per_page],
                absolute_page,
            )
            pdf.showPage()
            absolute_page += 1
    pdf.save()
    truth = {
        "name": name,
        "pages": 13,
        "description": (
            "Disclosed dummy challenge-equivalent fixture; not the external review document. "
            "Four 14-column multi-page tables with full-width title rows and wrapped cells."
        ),
        "tables": tables,
        "injected_errors": [],
    }
    (directory / f"{name}.truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    workbook = Workbook()
    workbook.remove(workbook.active)
    for index, table in enumerate(tables, 1):
        sheet = workbook.create_sheet(f"Data {index}")
        sheet.append(table["headers"])
        for row in table["rows"]:
            sheet.append(row)
    workbook.save(directory / f"{name}.truth.xlsx")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "samples")
    args = parser.parse_args()
    write_fixture(args.output)
    print(f"Generated {args.output / 'G_thirteen_page_equivalent.pdf'}")


if __name__ == "__main__":
    main()
