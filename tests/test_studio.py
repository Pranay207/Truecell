"""Workflow checks for the source inspector, equation preview and actual mutation lab."""

from streamlit.testing.v1 import AppTest

from eval.generate_samples import bank_sample, invoice_sample
from truecell.assurance import challenge
from truecell.pipeline import convert
from truecell.review import fingerprint
from truecell.values import number


def test_real_source_inspector_and_equation_preview(tmp_path):
    bank_sample(tmp_path)
    source = tmp_path / "B_bank_errors.pdf"
    result = convert(source)
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = {
        "result": result,
        "source": str(source),
        "name": "bank.xlsx",
    }
    app.run(timeout=30)
    assert not app.exception
    next(b for b in app.button if b.label == "Preview the effect without saving").click()
    app.run(timeout=30)
    assert not app.exception
    assert any("from 2 to 0" in i.value for i in app.info)
    assert app.session_state["conversion"]["result"].tables[0].rows[10][5] == "1081.00"


def test_challenge_invokes_actual_validator_without_editing_data(tmp_path):
    invoice_sample(tmp_path)
    result = convert(tmp_path / "A_invoice_register.pdf")
    before = fingerprint(result)
    report = challenge(result.tables[0], 12)
    assert report["tested"] == 12 and report["caught"] > 0
    assert fingerprint(result) == before
    assert all(case["original"] != case["mutated"] for case in report["cases"])


def test_unmodeled_columns_can_miss_injections():
    from truecell.models import Table

    table = Table(
        ["A", "B"],
        [[f"item{i}", str(10 + i)] for i in range(8)],
        1,
        (0, 0, 10, 10),
        "native",
    )
    report = challenge(table, 8)
    assert report["caught"] == 0 and report["tested"] == 8
    assert 2 in report["unmodeled_columns"]


def test_percentage_and_indian_grouping():
    from decimal import Decimal

    assert number("18%") == Decimal(".18")
    assert number("₹1,23,456.78") == Decimal("123456.78")
    assert number("123.45 INR") == Decimal("123.45")
    assert number("12,34") is None


def test_no_cloud_call_without_explicit_opt_in(monkeypatch, tmp_path):
    import truecell.llm_repair as llm

    bank_sample(tmp_path)
    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(
        llm,
        "extract_page",
        lambda *a: (_ for _ in ()).throw(AssertionError("network must not run")),
    )
    result = convert(tmp_path / "B_bank_errors.pdf")
    assert all(a.engine != "vision-llm" for p in result.pages for a in p.attempts)


def test_evidence_page_coordinates_survive_right_angle_rotation():
    import numpy as np

    from truecell.geometry import rotation_to_original, transformed_box

    assert transformed_box([10, 20, 40, 60], rotation_to_original(90, 200, 100)) == [
        140,
        10,
        180,
        40,
    ]
    assert transformed_box([10, 20, 40, 60], np.eye(3), 0.5, 0.5) == [5, 10, 20, 30]
