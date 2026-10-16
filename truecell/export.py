"""Safe, typed Excel export with separate audit and provenance sheets."""

from __future__ import annotations

import math
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

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
        if value.strip().endswith("%"):
            cell.number_format = "0.00%" if "." in value else "0%"
        else:
            precision = (
                min(12, len(value.split(".", 1)[1].split()[0].rstrip(")"))) if "." in value else 0
            )
            cell.number_format = "#,##0" + ("." + "0" * precision if precision else "")
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
    evidence_rows = []
    for index, table in enumerate(result.tables, 1):
        sheet = workbook.create_sheet(f"Data {index}")
        for col, header in enumerate(table.headers, 1):
            safe_text(sheet.cell(1, col), header)
            if table.header_sources[col - 1]:
                sheet.cell(1, col).hyperlink = f"#'Cell Evidence'!A{len(evidence_rows) + 2}"
            for record in table.header_sources[col - 1]:
                evidence_rows.append(
                    [
                        sheet.title,
                        1,
                        col,
                        record.get("page"),
                        *(record.get("bbox") or [None] * 4),
                        record.get("engine"),
                        record.get("confidence"),
                        record.get("text"),
                        record.get("initial_reading", ""),
                        record.get("role", "header"),
                    ]
                )
        for row_no, row in enumerate(table.rows, 2):
            for col, value in enumerate(row, 1):
                write_value(sheet.cell(row_no, col), value)
                sources = table.cell_sources[row_no - 2][col - 1]
                if sources:
                    sheet.cell(
                        row_no, col
                    ).hyperlink = f"#'Cell Evidence'!A{len(evidence_rows) + 2}"
                for record in sources:
                    bbox = record.get("bbox") or [None] * 4
                    evidence_rows.append(
                        [
                            sheet.title,
                            row_no,
                            col,
                            record.get("page"),
                            *bbox,
                            record.get("engine"),
                            record.get("confidence"),
                            record.get("text"),
                            record.get("initial_reading", ""),
                            record.get("role", "extracted"),
                        ]
                    )
            for page, source_row in table.provenance[row_no - 2]:
                provenance.append(
                    [
                        sheet.title,
                        row_no,
                        page,
                        source_row,
                        table.row_engines[row_no - 2],
                    ]
                )
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
    sheet.append(
        [
            "Severity",
            "Page",
            "Source row",
            "Column",
            "Table",
            "Code",
            "Reason",
            "Suggested action",
        ]
    )
    for issue in result.issues:
        sheet.append(
            [
                issue.severity,
                issue.page,
                issue.row,
                issue.column,
                issue.table,
                issue.code,
                issue.reason,
                issue.suggestion,
            ]
        )
    if not result.issues:
        sheet.append(
            [
                "info",
                None,
                None,
                None,
                None,
                "no_findings",
                "No implemented rule raised a finding. This is not proof of accuracy.",
                "Compare with the source.",
            ]
        )
    sheet = workbook.create_sheet("Page Audit")
    sheet.append(
        [
            "Page",
            "Route",
            "Engine",
            "Confidence",
            "Seconds",
            "Strategy",
            "Selected",
            "Tables",
            "Cells",
            "Findings",
            "Score",
            "Error",
        ]
    )
    for page in result.pages:
        if not page.attempts:
            sheet.append(
                [
                    page.page,
                    page.route,
                    page.engine,
                    page.confidence,
                    page.seconds,
                    "",
                    True,
                    0,
                    0,
                    0,
                    0,
                    page.error,
                ]
            )
        for attempt in page.attempts:
            sheet.append(
                [
                    page.page,
                    page.route,
                    attempt.engine,
                    page.confidence,
                    round(attempt.seconds, 3),
                    attempt.strategy,
                    attempt.selected,
                    attempt.tables,
                    attempt.cells,
                    attempt.issues,
                    attempt.score,
                    attempt.error,
                ]
            )
    sheet = workbook.create_sheet("Provenance")
    sheet.append(["Data sheet", "Excel row", "PDF page", "Source table data row", "Engine"])
    for row in provenance:
        sheet.append(row)
    sheet = workbook.create_sheet("Read me")
    sheet.append(["Field", "Value"])
    sheet.append(["Source", result.source])
    sheet.append(["Runtime seconds", round(result.seconds, 3)])
    sheet.append(
        [
            "Yellow cells",
            "Review required. See Validation Report for the reason and source row.",
        ]
    )
    sheet.append(
        [
            "Source row",
            "Data row within the extracted source table, excluding detected headers.",
        ]
    )
    sheet.append(
        [
            "Confidence",
            "Extraction heuristic / OCR score, not a calibrated probability of correctness.",
        ]
    )
    sheet.append(
        [
            "Dates",
            "ISO and unambiguous day-first dates are typed. Ambiguous dates stay text.",
        ]
    )
    sheet.append(
        [
            "Safety",
            "Source strings are stored as text. No source formulas are executed.",
        ]
    )
    sheet.append(
        [
            "Cell evidence",
            "Ctrl+click a linked data cell for its source bounding box and original readings.",
        ]
    )
    sheet.append(
        [
            "Repair proposals",
            "Arithmetic-derived suggestions only. Source documents may contain errors. Never applied automatically.",
        ]
    )
    sheet = workbook.create_sheet("Cell Evidence")
    sheet.append(
        [
            "Data sheet",
            "Excel row",
            "Column",
            "Source page",
            "x0",
            "y0",
            "x1",
            "y1",
            "Engine",
            "OCR score",
            "Reading",
            "Initial reading",
            "Role",
        ]
    )
    for row in evidence_rows:
        sheet.append(row)
    from .constraints import coverage
    from .review import fingerprint, review_current

    sheet = workbook.create_sheet("Verification")
    sheet.append(["Evidence", "Value"])
    sheet.append(["Source SHA-256", result.source_sha256])
    sheet.append(["Extraction snapshot SHA-256", fingerprint(result)])
    sheet.append(
        [
            "Review status",
            "Reviewed current snapshot" if review_current(result) else "Unreviewed",
        ]
    )
    sheet.append(
        [
            "Review meaning",
            "A human source-check attestation; not independent accuracy certification.",
        ]
    )
    sheet.append(["Review note", result.review.get("note", "") if review_current(result) else ""])
    for name, value in coverage(result).items():
        sheet.append([name.replace("_", " "), value])
    sheet = workbook.create_sheet("Constraints")
    sheet.append(
        [
            "ID",
            "Table",
            "Inferred relation",
            "Checked rows",
            "Matching rows",
            "Empirical agreement",
            "Violations",
            "Meaning",
        ]
    )
    for relation in result.constraints:
        sheet.append(
            [
                relation["id"],
                relation["table"],
                relation["formula"],
                relation["checked"],
                relation["matched"],
                relation["support"],
                len(relation["violations"]),
                "Inferred from this document; not a probability of correctness.",
            ]
        )
        sheet.cell(sheet.max_row, 6).number_format = "0.0%"
    sheet = workbook.create_sheet("Repair Proposals")
    sheet.append(
        [
            "Table",
            "Excel row",
            "Column",
            "Observed",
            "Proposed",
            "Supporting equations",
            "Evidence",
            "State",
            "Caution",
        ]
    )
    for proposal in result.proposals:
        sheet.append(
            [
                proposal["table"],
                proposal["row"] + 2,
                proposal["column"] + 1,
                proposal["observed"],
                proposal["proposed"],
                proposal["support_count"],
                "; ".join(proposal["supporting_equations"]),
                proposal["status"],
                proposal["basis"],
            ]
        )
    sheet = workbook.create_sheet("Correction History")
    sheet.append(
        [
            "Time UTC",
            "Table",
            "Excel row",
            "Column",
            "Before",
            "After",
            "Reason",
            "Previous hash",
            "Event hash",
        ]
    )
    for event in result.history:
        sheet.append(
            [
                event["at"],
                event["table"] + 1,
                event["row"] + 2,
                event["column"] + 1,
                event["before"],
                event["after"],
                event["note"],
                event["previous"],
                event["sha256"],
            ]
        )
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
