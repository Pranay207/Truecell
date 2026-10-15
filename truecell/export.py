"""Safe, typed Excel export with separate audit and provenance sheets."""
from __future__ import annotations

from pathlib import Path
import math
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Result
from .values import date_value, is_identifier, number

NAVY = "17324D"
YELLOW = PatternFill("solid", fgColor="FFF0B3")


def safe_text(cell, value: str) -> None:
    """Set an explicit string type, preventing spreadsheet formula injection."""
    cell.value = value
    cell.data_type = "s"


def write_value(cell, value: str) -> None:
    """Type only unambiguous values; preserve IDs and precision-sensitive data."""
    if is_identifier(value):
        safe_text(cell, value)
        cell.number_format = "@"
    elif (parsed := number(value)) is not None and len(parsed.as_tuple().digits) <= 15:
        cell.value = float(parsed) if parsed % 1 else int(parsed)
        cell.number_format = "#,##0.00" if "." in value else "#,##0"
    elif (parsed_date := date_value(value)) is not None:
        cell.value = parsed_date
        cell.number_format = "yyyy-mm-dd"
    else:
        safe_text(cell, value)


def style_sheet(sheet) -> None:
    """Apply readable, compact formatting to every populated sheet."""
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.showGridLines = False
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name="Calibri", color="FFFFFF", bold=True, size=11)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 32
    for column in sheet.columns:
        length = max(len(str(c.value or "")) for c in column)
        sheet.column_dimensions[column[0].column_letter].width = min(65, max(13, length + 2))
    for row in sheet.iter_rows(min_row=2):
        line_count = 1
        for cell in row:
            cell.font = Font(name="Calibri", size=11)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            width = sheet.column_dimensions[cell.column_letter].width
            line_count = max(line_count, math.ceil(len(str(cell.value or "")) / max(1, width - 2)))
        sheet.row_dimensions[row[0].row].height = min(409, 17 * line_count)


def export_workbook(result: Result, output: str | Path) -> Path:
    """Write data, every validation finding, page attempts and source row mapping."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    provenance = []
    for index, table in enumerate(result.tables, 1):
        sheet = workbook.create_sheet(f"Data {index}")
        for col, header in enumerate(table.headers, 1):
            safe_text(sheet.cell(1, col), header)
        for row_no, row in enumerate(table.rows, 2):
            for col, value in enumerate(row, 1):
                write_value(sheet.cell(row_no, col), value)
            for page, source_row in table.provenance[row_no - 2]:
                provenance.append([sheet.title, row_no, page, source_row, table.row_engines[row_no-2]])
        for issue in result.issues:
            if issue.table != index:
                continue
            for r, sources in enumerate(table.provenance, 2):
                if issue.row is not None and (issue.page, issue.row) not in sources:
                    continue
                if issue.row is None and not any(p == issue.page for p, _ in sources):
                    continue
                columns = [issue.column] if issue.column else range(1, len(table.headers) + 1)
                for col in columns:
                    sheet.cell(r, col).fill = YELLOW
    sheet = workbook.create_sheet("Validation Report")
    sheet.append(["Severity", "Page", "Source row", "Column", "Table", "Code", "Reason", "Suggested action"])
    for issue in result.issues:
        sheet.append([issue.severity, issue.page, issue.row, issue.column,
                      issue.table, issue.code, issue.reason, issue.suggestion])
    if not result.issues:
        sheet.append(["info", None, None, None, None, "no_findings",
                      "No implemented rule raised a finding. This is not proof of accuracy.", "Compare with the source."])
    sheet = workbook.create_sheet("Page Audit")
    sheet.append(["Page", "Route", "Engine", "Confidence", "Seconds", "Strategy", "Selected",
                  "Tables", "Cells", "Findings", "Score", "Error"])
    for page in result.pages:
        if not page.attempts:
            sheet.append([page.page, page.route, page.engine, page.confidence, page.seconds,
                          "", True, 0, 0, 0, 0, page.error])
        for attempt in page.attempts:
            sheet.append([page.page, page.route, attempt.engine, page.confidence,
                          round(attempt.seconds, 3), attempt.strategy, attempt.selected,
                          attempt.tables, attempt.cells, attempt.issues, attempt.score, attempt.error])
    sheet = workbook.create_sheet("Provenance")
    sheet.append(["Data sheet", "Excel row", "PDF page", "Source table data row", "Engine"])
    for row in provenance:
        sheet.append(row)
    sheet = workbook.create_sheet("Read me")
    sheet.append(["Field", "Value"])
    sheet.append(["Source", result.source])
    sheet.append(["Runtime seconds", round(result.seconds, 3)])
    sheet.append(["Yellow cells", "Review required. See Validation Report for the reason and source row."])
    sheet.append(["Source row", "Data row within the extracted source table, excluding detected headers."])
    sheet.append(["Confidence", "Extraction heuristic / OCR score, not a calibrated probability of correctness."])
    sheet.append(["Dates", "ISO and unambiguous day-first dates are typed. Ambiguous dates stay text."])
    sheet.append(["Safety", "Source strings are stored as text. No source formulas are executed."])
    for sheet in workbook:
        style_sheet(sheet)
    # Force text types in audit metadata as well as data cells.
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return target
