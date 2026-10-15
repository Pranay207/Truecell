"""Header-independent checks and cases where arithmetic must not be invented."""
from decimal import Decimal

import pytest

from eval.generate_samples import bank_sample
from truecell.models import Table
from truecell.pipeline import convert
from truecell.validate import validate, classify_columns, tolerance, total_row


def table(rows, headers=None, engine="native"):
    return Table(headers or [f"K{i}" for i in range(len(rows[0]))], rows, 1, (0,0,100,100), engine)


def test_injected_bank_errors(tmp_path):
    bank_sample(tmp_path)
    result = convert(tmp_path / "B_bank_errors.pdf",tmp_path / "bank.xlsx")
    assert any(i.code == "total_mismatch" and i.row == 19 and i.column == 4 for i in result.issues)
    assert any(i.code == "running_balance" and i.row == 11 and i.column == 6 for i in result.issues)
    from openpyxl import load_workbook
    workbook=load_workbook(tmp_path/"bank.xlsx")
    assert workbook["Data 1"]["D20"].fill.fgColor.rgb=="00FFF0B3"
    assert workbook["Data 1"]["F12"].fill.fgColor.rgb=="00FFF0B3"


def test_discovered_multiplication():
    rows = [[f"R{i}", str(i), str(i+2), str(i*(i+2))] for i in range(1, 11)]
    rows[7][3] = "999"
    findings = validate(table(rows))
    assert any(i.code == "row_arithmetic" and i.row == 8 and i.column == 4 for i in findings)


def test_short_table_no_arithmetic_inference():
    findings = validate(table([["A", "2", "3", "6"], ["B", "3", "4", "99"]]))
    assert not any(i.code == "row_arithmetic" for i in findings)


def test_total_keyword_any_cell():
    findings = validate(table([["A", "10.00", "x"], ["B", "20.00", "x"], ["", "31.00", "Total"]]))
    assert any(i.code == "total_mismatch" and i.column == 2 for i in findings)


def test_subtotal_then_grand_total_excludes_subtotals():
    rows = [["A", "10.00"], ["Subtotal", "10.00"], ["B", "20.00"],
            ["Subtotal", "20.00"], ["Grand Total", "30.00"]]
    assert not any(i.code == "total_mismatch" for i in validate(table(rows)))


def test_decimal_rounding_exact():
    rows = [["A", "0.10"], ["B", "0.20"], ["Total", "0.30"]]
    assert not any(i.code == "total_mismatch" for i in validate(table(rows)))


@pytest.mark.parametrize("rows,code", [
    ([["A","1",""],["B","2",""]], "empty_column"),
    ([["A","1"],["A","1"]], "duplicate_row"),
    ([["A","1"],["B","2"],["C","oops"]], "type_mismatch"),
    ([["A","1"],["B"]], "column_count"),
    ([["A","1","2","3","4","5"],["B","","","","",""]], "sparse_row"),
    ([["A","13/10/2026"],["B","14/10/2026"],["C","2026-10-15"]], "date_format"),
    ([["A","01/02/2026"],["B","02/03/2026"]], "ambiguous_date"),
])
def test_structural_findings(rows,code):
    assert code in {i.code for i in validate(table(rows))}


@pytest.mark.parametrize("row,expected", [(["Total","2"],True),(["item","Subtotal"],True),(["balance transfer","2"],False),(["sum","2"],True),(["totality","2"],False)])
def test_total_detection(row,expected):
    assert total_row(row) == expected


def test_content_classification():
    assert classify_columns(table([["001","1.00","2026-10-13","x"],["002","₹2.00","2026-10-14","y"]])) == ["id","numeric","date","text"]


@pytest.mark.parametrize("values,expected", [(["1.00","2.00"],"0.005"),(["1","2"],"0.5"),(["1.0","2.00"],"0.05")])
def test_rounding_tolerance(values,expected):
    assert tolerance(values) == Decimal(expected)


def test_ocr_confusable_not_corrected():
    t = table([["A","12.00"],["B","13.00"],["C","1O.00"]], engine="ocr-test")
    assert any(i.code == "ocr_digit_risk" for i in validate(t))
    assert t.rows[-1][-1] == "1O.00"
