"""Application-level render checks for upload and saved results."""

import pytest
from streamlit.testing.v1 import AppTest

from truecell.models import Attempt, Issue, PageReport, Result, Table


def test_initial_ui_loads():
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert next(b for b in app.button if b.label == "Extract tables").disabled


def test_result_preview_handles_duplicate_labels_and_ragged_rows():
    result = Result(
        "dummy",
        [
            Table(
                ["Same", "Same"],
                [["001", "12"], ["002", "13", "extra"]],
                1,
                (0, 0, 10, 10),
                "native",
            )
        ],
    )
    result.issues = [Issue("warning", 1, 2, 3, "Unexpected extra column", table=1)]
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = {
        "result": result,
        "xlsx": b"test",
        "name": "test.xlsx",
    }
    app.run(timeout=30)
    assert not app.exception
    assert app.metric[2].value == "2"


def test_finding_focus_opens_its_source_row_and_column():
    result = Result(
        "dummy",
        [
            Table(
                ["Ref", "Amount", "Memo"],
                [["001", "10", "A"], ["002", "bad", "B"]],
                1,
                (0, 0, 100, 100),
                "native",
            )
        ],
    )
    result.issues = [Issue("warning", 1, 2, 2, "Amount is text", table=1)]
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = {"result": result, "xlsx": b"test", "name": "test.xlsx"}
    app.session_state["row_0"] = 999
    app.session_state["col_0"] = 999
    app.run(timeout=30)
    assert not app.exception
    next(b for b in app.button if b.label == "Inspect finding").click().run(timeout=30)
    assert not app.exception
    assert next(n for n in app.number_input if n.label == "Data row").value == 2
    assert next(s for s in app.selectbox if s.label == "Column").value == 1


def test_no_table_result_keeps_audit_errors_and_downloads_reachable():
    result = Result(
        "no-table.pdf",
        pages=[
            PageReport(
                1,
                "digital",
                attempts=[Attempt("native", "lines", 0, 0, 0, 0, 0.1, error="Grid failed")],
            ),
            PageReport(2, "ocr", error="Page rendering failed"),
        ],
    )
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = {"result": result, "name": "no-table.xlsx"}
    app.run(timeout=30)
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Review & export", "Engine audit"]
    assert len(app.get("download_button")) == 2
    audit = app.dataframe[-1].value
    assert "Grid failed" in audit["error"].tolist()
    assert "Page rendering failed" in audit["error"].tolist()


@pytest.mark.parametrize("source_bytes", [None, b"not a readable PDF"])
def test_unavailable_source_keeps_current_result_and_downloads(tmp_path, source_bytes):
    source = tmp_path / "source.pdf"
    if source_bytes is not None:
        source.write_bytes(source_bytes)
    table = Table(["Ref", "Amount"], [["001", "12"]], 1, (0, 0, 100, 100), "native")
    table.cell_sources[0][0] = [
        {"page": 1, "bbox": [0, 0, 20, 20], "text": "001", "engine": "native"}
    ]
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = {
        "result": Result("dummy.pdf", [table]),
        "source": str(source),
        "name": "dummy.xlsx",
    }
    app.run(timeout=30)
    assert not app.exception
    assert any("Source preview unavailable" in error.value for error in app.error)
    assert len(app.get("download_button")) == 2


def _dummy_saved(name):
    return {
        "result": Result(
            name, [Table(["Ref", "Amount"], [["001", "12"]], 1, (0, 0, 10, 10), "native")]
        ),
        "name": name + ".xlsx",
    }


def test_document_switch_requires_a_fresh_source_check():
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = _dummy_saved("A")
    app.run(timeout=30)
    next(c for c in app.checkbox if c.label.startswith("I checked the original")).check()
    next(t for t in app.text_area if t.label == "Review note and accepted findings").set_value(
        "Source A only"
    )
    app.run(timeout=30)
    app.session_state["conversion"] = _dummy_saved("B")
    app.run(timeout=30)
    assert not app.exception
    assert not next(c for c in app.checkbox if c.label.startswith("I checked the original")).value
    assert (
        next(t for t in app.text_area if t.label == "Review note and accepted findings").value == ""
    )


def test_cell_edit_clears_pending_review_attestation():
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = _dummy_saved("A")
    app.run(timeout=30)
    next(c for c in app.checkbox if c.label.startswith("I checked the original")).check()
    next(t for t in app.text_area if t.label == "Review note and accepted findings").set_value(
        "Previous snapshot only"
    )
    app.run(timeout=30)
    next(t for t in app.text_input if t.label == "Reviewed value").set_value("002")
    next(t for t in app.text_area if t.label == "Reason for change").set_value("Dummy source check")
    next(b for b in app.button if b.label == "Save correction").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["conversion"]["result"].tables[0].rows[0][0] == "002"
    assert not next(c for c in app.checkbox if c.label.startswith("I checked the original")).value
    assert (
        next(t for t in app.text_area if t.label == "Review note and accepted findings").value == ""
    )


def test_selecting_another_proposal_requires_a_fresh_source_check():
    saved = _dummy_saved("A")
    result = saved["result"]
    result.tables[0] = Table(
        ["Ref", "Amount"], [["001", "12"], ["002", "14"]], 1, (0, 0, 10, 10), "native"
    )
    result.proposals = [
        {
            "table": 1,
            "row": row,
            "column": 1,
            "observed": value,
            "proposed": "13",
            "support_count": 2,
            "supporting_equations": ["Dummy equation receipt"],
            "status": "proposal",
            "basis": "Dummy arithmetic evidence",
        }
        for row, value in enumerate(["12", "14"])
    ]
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = saved
    app.run(timeout=30)
    next(c for c in app.checkbox if c.label.startswith("I inspected the source")).check()
    next(t for t in app.text_input if t.label == "Correction reason").set_value("First cell only")
    app.run(timeout=30)
    next(s for s in app.selectbox if s.label == "Inspect a proposal").select(
        result.proposals[1]
    ).run(timeout=30)
    assert not app.exception
    assert not next(c for c in app.checkbox if c.label.startswith("I inspected the source")).value
    assert next(t for t in app.text_input if t.label == "Correction reason").value == ""


def test_missing_baseline_keeps_working_export_available(monkeypatch):
    import truecell.ui as ui

    saved = _dummy_saved("A")
    saved["job_id"] = "a" * 32

    def unavailable(*args, **kwargs):
        raise ValueError("Saved source changed")

    monkeypatch.setattr(ui, "load_result", unavailable)
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = saved
    app.run(timeout=30)
    assert not app.exception
    assert any("Original extraction unavailable" in error.value for error in app.error)
    assert len(app.get("download_button")) == 2


def test_failed_correction_save_keeps_working_copy_and_downloads(monkeypatch):
    import truecell.ui as ui

    saved = _dummy_saved("A")
    saved["job_id"] = "a" * 32
    original = saved["result"]
    monkeypatch.setattr(ui, "load_result", lambda *args, **kwargs: original)

    def unwritable(*args, **kwargs):
        raise OSError("Workspace became unwritable")

    monkeypatch.setattr(ui, "save_result", unwritable)
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = saved
    app.run(timeout=30)
    next(t for t in app.text_input if t.label == "Reviewed value").set_value("002")
    next(t for t in app.text_area if t.label == "Reason for change").set_value("Dummy source check")
    next(b for b in app.button if b.label == "Save correction").click().run(timeout=30)
    assert not app.exception
    assert any("Workspace became unwritable" in error.value for error in app.error)
    current = app.session_state["conversion"]["result"]
    assert current.tables[0].rows[0][0] == "001"
    assert not current.history
    assert len(app.get("download_button")) == 3


@pytest.mark.parametrize("failure", ["create", "status"])
def test_workspace_io_failure_keeps_prior_result_and_downloads(monkeypatch, failure):
    import truecell.ui as ui

    saved = _dummy_saved("Previous document")
    status_calls = []

    def create(*args, **kwargs):
        if failure == "create":
            raise OSError("Cannot create output folder")
        return "a" * 32, ui.PROJECT / "samples" / "A_invoice_register.pdf"

    def status(*args, **kwargs):
        status_calls.append(args[1])
        raise OSError("Cannot update workspace status")

    monkeypatch.setattr(ui, "create_job", create)
    monkeypatch.setattr(ui, "set_status", status)
    app = AppTest.from_file("app.py")
    app.session_state["conversion"] = saved
    app.run(timeout=30)
    next(b for b in app.button if b.label == "Invoice register").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["conversion"]["result"].source == "Previous document"
    assert app.session_state["conversion"]["result"].tables[0].rows[0][0] == "001"
    assert len(app.get("download_button")) == 2
    expected = (
        "Cannot create output folder" if failure == "create" else "Cannot update workspace status"
    )
    assert any(expected in error.value for error in app.error)
    if failure == "status":
        assert status_calls == ["processing", "failed"]


def test_resume_preserves_an_existing_reviewed_working_copy(monkeypatch, tmp_path):
    import truecell.ui as ui

    source = tmp_path / "source.pdf"
    source.write_bytes(b"dummy source")
    result = _dummy_saved("A")["result"]
    result.review = {"status": "reviewed"}
    monkeypatch.setattr(ui, "load_result", lambda _: result)
    monkeypatch.setattr(ui, "job_path", lambda _: tmp_path)
    calls = []
    monkeypatch.setattr(ui, "_run", lambda *args: calls.append(("new", args)))
    monkeypatch.setattr(ui, "_process", lambda *args: calls.append(("existing", args)))
    ui._resume(
        {"id": "a" * 32, "source": source.name, "name": "dummy.pdf", "options": {"force": True}}
    )
    assert calls == [("new", ("dummy.pdf", b"dummy source", False, True))]


def test_resume_reuses_checkpoints_for_unedited_partial_result(monkeypatch, tmp_path):
    import truecell.ui as ui

    result = _dummy_saved("A")["result"]
    result.review = {"status": "unreviewed"}
    monkeypatch.setattr(ui, "load_result", lambda _: result)
    monkeypatch.setattr(ui, "job_path", lambda _: tmp_path)
    calls = []
    monkeypatch.setattr(ui, "_run", lambda *args: calls.append(("new", args)))
    monkeypatch.setattr(ui, "_process", lambda *args: calls.append(("existing", args)))
    ui._resume({"id": "a" * 32, "source": "source.pdf", "name": "dummy.pdf"})
    assert calls == [("existing", ("a" * 32, tmp_path / "source.pdf", "dummy.pdf", False, False))]
