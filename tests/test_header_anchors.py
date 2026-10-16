"""Independent synthetic geometry cases for header-guided reconstruction."""

import json

import pytest
from openpyxl import load_workbook

from truecell.anchors import header_tables
from truecell.export import export_workbook
from truecell.models import Result, Table
from truecell.stitch import stitch


def line(values, y, bold=False):
    return [
        {
            "text": value,
            "x0": 25 + 155 * c,
            "x1": 25 + 155 * c + len(value) * 4,
            "top": y,
            "bottom": y + 10,
            "fontname": "Helvetica-Bold" if bold else "Helvetica",
        }
        for c, value in enumerate(values)
        if value
    ]


def test_sparse_text_matrix_and_wrapped_cell_keep_columns():
    words = (
        line(["Team", "Monday", "Tuesday", "Wednesday"], 20, True)
        + line(["Blue", "Planning", "", "Review"], 45)
        + line(["", "continued", "", ""], 58)
        + line(["Green", "", "Design", ""], 85)
        + line(["Amber", "Support", "", "Build"], 115)
    )
    table = header_tables(words, 1)[0]
    assert table.rows == [
        ["Blue", "Planning continued", "", "Review"],
        ["Green", "", "Design", ""],
        ["Amber", "Support", "", "Build"],
    ]
    assert table.cell_sources[0][1][0]["text"] == "Planning continued"
    assert table.cell_sources[0][1][0]["bbox"][3] == 68


def test_sparse_numeric_record_is_not_folded_into_previous_row():
    words = (
        line(["Ref", "Units", "Amount"], 20, True)
        + line(["A", "2", "10"], 45)
        + line(["", "", "7"], 58)
        + line(["B", "3", "15"], 85)
    )
    assert header_tables(words, 1)[0].rows == [["A", "2", "10"], ["", "", "7"], ["B", "3", "15"]]


def test_continuity_summary_survives_stitch_serialization_and_export(tmp_path):
    words = (
        line(["Date", "Memo", "Balance"], 20, True)
        + line(["01/02/2026", "Sale", "120"], 45)
        + line(["02/02/2026", "Refund", "110"], 70)
        + line(["", "Carried forward", "110"], 95)
    )
    first = header_tables(words, 1)[0]
    second = header_tables([{**w} for w in words], 2)[0]
    joined, _ = stitch([first, second])
    assert len(joined) == 1 and len(joined[0].rows) == 4
    restored = Table.from_dict(joined[0].to_dict())
    assert len(restored.page_summaries) == 2
    export = export_workbook(Result("dummy.pdf", [restored]), tmp_path / "summary.xlsx")
    sheet = load_workbook(export)["Page Summaries"]
    assert sheet.max_row == 3
    assert [sheet.cell(r, 2).value for r in (2, 3)] == [1, 2]
    assert sheet["D2"].value == "Carried forward 110"


def test_bold_total_is_not_a_new_header():
    words = (
        line(["Ref", "Units", "Amount"], 20, True)
        + line(["A", "2", "10"], 45)
        + line(["B", "3", "15"], 70)
        + line(["Total", "5", "25"], 95, True)
    )
    table = header_tables(words, 1)[0]
    assert table.rows[-1] == ["Total", "5", "25"]


def test_bold_numeric_rows_with_spaced_decimals_are_not_headers():
    words = (
        line(["Crime", "Total", "Male", "Female"], 20, True)
        + line(["Theft", "467 .9", "69 .1", "398 .8"], 45, True)
        + line(["Fraud", "380 .2", "56 .5", "323 .7"], 75, True)
        + line(["Other", "87 .7", "12 .6", "75 .2"], 105)
    )
    tables = header_tables(words, 1)
    assert len(tables) == 1 and len(tables[0].rows) == 3
    assert tables[0].rows[0][1] == "467 .9"


def test_aligned_prose_without_header_evidence_is_not_a_table():
    words = line(["Review", "the", "document"], 20) + line(["Check", "the", "source"], 45)
    assert header_tables(words, 1) == []


def test_ocr_headers_preserve_alternating_empty_amount_columns():
    rows = [
        ["D1", "Sale", "001", "", "40.00", "140.00"],
        ["D2", "Rent", "002", "20.00", "", "120.00"],
        ["D3", "Sale", "003", "", "50.00", "170.00"],
        ["D4", "Fuel", "004", "10.00", "", "160.00"],
    ]
    words = line(["Date", "Memo", "Reference", "Debit", "Credit", "Balance"], 40)
    words += [w for r, row in enumerate(rows) for w in line(row, 70 + r * 30)]
    words = [{**w, "confidence": 0.99} for w in words]
    table = header_tables(words, 1, engine="ocr-test-anchors", font_evidence=False)[0]
    assert table.rows == rows
    assert len(table.headers) == 6
    assert table.cell_sources[0][4][0]["confidence"] == 0.99


def test_native_prose_does_not_start_ocr_and_invent_a_grid(tmp_path, monkeypatch):
    from reportlab.pdfgen.canvas import Canvas

    import truecell.ocr as ocr
    from truecell.pipeline import convert

    source = tmp_path / "letter.pdf"
    canvas = Canvas(str(source))
    for i, text in enumerate(
        [
            "This letter describes the review process for a document.",
            "Please read the original page before making any changes.",
            "The author has included no tables in this short message.",
        ]
    ):
        canvas.drawString(40, 720 - i * 18, text)
    canvas.save()
    monkeypatch.setattr(
        ocr, "available_engines", lambda: (_ for _ in ()).throw(AssertionError("OCR"))
    )
    result = convert(source)
    assert result.tables == []
    assert any(i.code == "no_table" for i in result.issues)


@pytest.fixture(scope="module")
def layouts(tmp_path_factory):
    from eval.generate_layouts import generate

    directory = tmp_path_factory.mktemp("native-layouts")
    generate(directory)
    return directory


@pytest.mark.parametrize(
    "name",
    [
        "E_sparse_schedule",
        "E_wrapped_contacts",
        "E_page_carry",
        "E_unruled_totals",
        "E_eighteen_columns",
        "E_no_table_letter",
        "E_vertical_nested_lines",
    ],
)
def test_native_pdf_layouts_match_literal_source(layouts, name):
    from eval.score import score
    from truecell.pipeline import convert

    truth = json.loads((layouts / f"{name}.truth.json").read_text())
    result = convert(layouts / f"{name}.pdf")
    assert score(truth, result)["pass"]
    if name == "E_page_carry":
        assert len(result.tables[0].page_summaries) == 2
    if name == "E_wrapped_contacts":
        assert result.tables[0].rows[0][0] == "001"
    if name == "E_vertical_nested_lines":
        table = result.tables[0]
        assert table.engine == "native-lines"
        assert [row[0] for row in table.rows] == ["WP-100"] * 4 + ["WP-200"] * 4
        assert table.cell_sources[1][0][0]["role"] == "vertical_merge_expansion"
        assert table.cell_sources[0][0][0]["bbox"] == table.cell_sources[1][0][0]["bbox"]
