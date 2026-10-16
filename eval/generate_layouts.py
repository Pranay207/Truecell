"""Additional independently authored dummy layouts, with literal-source truth.

These are regression/development cases, not an independent or blind benchmark.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import fitz
from PIL import Image
from reportlab.pdfgen.canvas import Canvas

from .generate_samples import ROOT, draw_table, write_truth


def labels(pdf, row, y, xs, bold=False):
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
    for x, value in zip(xs, row):
        pdf.drawString(x, y, value)


def vertical_nested_sample(directory: Path) -> None:
    """Create nested line items whose group cells physically span child rows."""
    name = "E_vertical_nested_lines"
    headers = [
        "Package",
        "Phase",
        "Line",
        "Parent",
        "Description",
        "Unit",
        "Qty",
        "Rate",
        "Amount",
        "Status",
    ]
    rows = [
        ["WP-100", "Hardware", "1", "-", "Network gateway", "ea", "2", "120.00", "240.00", "Ready"],
        ["WP-100", "Hardware", "1.1", "1", "Cable pack", "pack", "3", "10.00", "30.00", "Ready"],
        ["WP-100", "Installation", "2", "-", "Site survey", "hr", "4", "25.00", "100.00", "Review"],
        ["WP-100", "Installation", "2.1", "2", "Rack setup", "hr", "3", "40.00", "120.00", "Ready"],
        ["WP-200", "Software", "3", "-", "Monitor license", "ea", "2", "180.00", "360.00", "Ready"],
        ["WP-200", "Software", "3.1", "3", "Support plan", "yr", "2", "35.00", "70.00", "Review"],
        ["WP-200", "Deployment", "4", "-", "Data migration", "hr", "8", "15.00", "120.00", "Review"],
        ["WP-200", "Deployment", "4.1", "4", "Final audit", "hr", "4", "20.00", "80.00", "Ready"],
    ]
    widths = [88, 100, 55, 60, 190, 50, 45, 70, 80, 75]
    x, top, row_height = 30, 500, 38
    xs = [x]
    for width in widths:
        xs.append(xs[-1] + width)
    pdf = Canvas(str(directory / f"{name}.pdf"), pagesize=(900, 560), invariant=1)
    pdf.setTitle("Nested line items with vertically merged groups")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(x, 530, "Nested work-package line items")
    pdf.setStrokeColorRGB(0.35, 0.45, 0.5)
    pdf.setLineWidth(0.7)
    bottom = top - row_height * (len(rows) + 1)
    for boundary in xs:
        pdf.line(boundary, top, boundary, bottom)
    pdf.line(xs[0], top, xs[-1], top)
    header_bottom = top - row_height
    pdf.line(xs[0], header_bottom, xs[-1], header_bottom)
    for row_index in range(len(rows)):
        y = header_bottom - (row_index + 1) * row_height
        if row_index in {0, 2, 4, 6}:
            start = xs[2]
        elif row_index in {1, 5}:
            start = xs[1]
        else:
            start = xs[0]
        pdf.line(start, y, xs[-1], y)
    pdf.setFont("Helvetica-Bold", 8)
    for column, value in enumerate(headers):
        pdf.drawString(xs[column] + 4, header_bottom + 14, value)
    pdf.setFont("Helvetica", 8)
    for row_index, row in enumerate(rows):
        baseline = header_bottom - (row_index + 1) * row_height + 14
        for column, value in enumerate(row[2:], 2):
            indent = 7 if column == 4 and "." in row[2] else 0
            pdf.drawString(xs[column] + 4 + indent, baseline, value)
    for start_row, value in ((0, "WP-100"), (4, "WP-200")):
        span_top = header_bottom - start_row * row_height
        span_bottom = span_top - 4 * row_height
        pdf.drawString(xs[0] + 4, (span_top + span_bottom) / 2 - 3, value)
    for start_row, value in (
        (0, "Hardware"),
        (2, "Installation"),
        (4, "Software"),
        (6, "Deployment"),
    ):
        span_top = header_bottom - start_row * row_height
        span_bottom = span_top - 2 * row_height
        pdf.drawString(xs[1] + 4, (span_top + span_bottom) / 2 - 3, value)
    pdf.save()
    write_truth(directory, name, [{"headers": headers, "rows": rows}], 1)


def generate(directory: Path) -> None:
    """Write varied native/scan documents without using external fixtures."""
    directory.mkdir(parents=True, exist_ok=True)
    vertical_nested_sample(directory)
    name = "E_sparse_schedule"
    headers = ["Team", "Monday", "Tuesday", "Wednesday", "Thursday"]
    rows = [
        ["Blue", "Planning", "", "Review", ""],
        ["Green", "", "Design", "", "Support"],
        ["Amber", "Build", "", "Support", ""],
        ["Violet", "", "Review", "", "Planning"],
    ]
    pdf = Canvas(str(directory / f"{name}.pdf"), pagesize=(700, 500))
    xs = [35, 155, 275, 395, 515]
    labels(pdf, headers, 440, xs, True)
    for i, row in enumerate(rows):
        labels(pdf, row, 405 - 32 * i, xs)
    pdf.save()
    write_truth(directory, name, [{"headers": headers, "rows": rows}], 1)

    name = "E_wrapped_contacts"
    headers = ["Contact ID", "Name", "Address", "City"]
    xs = [35, 135, 280, 520]
    pdf = Canvas(str(directory / f"{name}.pdf"), pagesize=(700, 500))
    labels(pdf, headers, 440, xs, True)
    rows = []
    for i, (person, city) in enumerate(
        [("Asha Rao", "Pune"), ("Hari Sen", "Kochi"), ("Mira Das", "Patna")]
    ):
        row = [f"00{i + 1}", person, f"{i + 12} Example Street", city]
        labels(pdf, row, 405 - i * 48, xs)
        labels(pdf, ["", "", "Building B, second floor", ""], 392 - i * 48, xs)
        rows.append([row[0], row[1], row[2] + " Building B, second floor", city])
    pdf.save()
    write_truth(directory, name, [{"headers": headers, "rows": rows}], 1)

    name = "E_page_carry"
    headers = ["Reference", "Memo", "Debit", "Credit", "Balance"]
    xs = [35, 135, 335, 435, 535]
    pdf = Canvas(str(directory / f"{name}.pdf"), pagesize=(700, 500))
    rows = []
    for page in range(2):
        labels(pdf, headers, 440, xs, True)
        for j in range(3):
            i = page * 3 + j
            row = [f"TX-{i + 1:03d}", "Dummy payment", "10.00", "", f"{990 - i * 10}.00"]
            labels(pdf, row, 405 - j * 32, xs)
            rows.append(row)
        labels(pdf, ["", "Carried forward", "", "", rows[-1][-1]], 295, xs)
        labels(pdf, [f"Page {page + 1} of 2"], 35, [35])
        pdf.showPage()
    pdf.save()
    write_truth(directory, name, [{"headers": headers, "rows": rows}], 2)

    name = "E_unruled_totals"
    headers = ["Record", "Description", "Units", "Unit price", "Amount"]
    rows = [
        ["A01", "Paper", "2", "12.00", "24.00"],
        ["A02", "Pens", "3", "5.00", "15.00"],
        ["A03", "Folders", "4", "7.00", "28.00"],
    ]
    pdf = Canvas(str(directory / f"{name}.pdf"), pagesize=(700, 500))
    draw_table(pdf, headers, rows, top=440, widths=[60, 190, 70, 90, 105])
    pdf.setFont("Helvetica", 9)
    for y, label, value in [
        (310, "Sub Total", "67.00"),
        (290, "Tax 10%", "6.70"),
        (270, "Grand Total", "73.70"),
    ]:
        pdf.drawString(100, y, label)
        pdf.drawRightString(545, y, value)
        rows.append(["", label, "", "", value])
    pdf.save()
    write_truth(directory, name, [{"headers": headers, "rows": rows}], 1)

    # Retain the same literal truth when rendering the entire invoice sideways.
    scan_name = "E_sideways_invoice"
    with fitz.open(directory / f"{name}.pdf") as source:
        pix = source[0].get_pixmap(dpi=220)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).rotate(90, expand=True)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    with fitz.open() as scan:
        page = scan.new_page(width=500, height=700)
        page.insert_image(page.rect, stream=buffer.getvalue())
        scan.save(directory / f"{scan_name}.pdf")
    write_truth(directory, scan_name, [{"headers": headers, "rows": rows}], 1)

    name = "E_eighteen_columns"
    headers = ["Ref"] + [f"M{i:02d}" for i in range(1, 18)]
    rows = [[f"R{r:02d}"] + [str(r * 20 + c) for c in range(1, 18)] for r in range(1, 10)]
    pdf = Canvas(str(directory / f"{name}.pdf"), pagesize=(1190, 500))
    draw_table(pdf, headers, rows, top=440, widths=[61] * 18, ruled=False)
    pdf.save()
    write_truth(directory, name, [{"headers": headers, "rows": rows}], 1)

    name = "E_no_table_letter"
    pdf = Canvas(str(directory / f"{name}.pdf"), pagesize=(700, 500))
    pdf.setFont("Helvetica", 11)
    for i, text in enumerate(
        [
            "Dear reviewer,",
            "This dummy letter describes a source review process.",
            "Please inspect the original document before making corrections.",
            "There are no tables or financial records on this page.",
            "Thank you for reading the document.",
        ]
    ):
        pdf.drawString(35, 440 - i * 22, text)
    pdf.save()
    write_truth(directory, name, [], 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "samples")
    generate(parser.parse_args().output)
