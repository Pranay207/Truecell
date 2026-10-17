"""End-user evidence, diagnosis, persistence and review safety scenarios."""

import json

import pytest
from openpyxl import load_workbook

from eval.generate_samples import bank_sample, invoice_sample
from truecell.checkpoint import Checkpoints
from truecell.constraints import analyze, coverage
from truecell.models import Result
from truecell.pipeline import convert
from truecell.review import (
    apply_edit,
    complete_review,
    fingerprint,
    history_valid,
    review_current,
    review_queue,
    set_item_review,
)
from truecell.workspace import create_job, job_path, load_result, save_result


@pytest.fixture
def bank(tmp_path):
    bank_sample(tmp_path)
    return convert(tmp_path / "B_bank_errors.pdf")


def test_diagnosis_uses_both_balance_transitions(bank):
    proposals = [p for p in bank.proposals if p["support_count"] >= 2]
    assert len(proposals) == 1
    assert (proposals[0]["row"], proposals[0]["column"], proposals[0]["proposed"]) == (
        10,
        5,
        "1064.00",
    )
    assert bank.tables[0].rows[10][5] == "1081.00"


def test_diagnosis_does_not_depend_on_header_labels(bank):
    bank.tables[0].headers = [f"Unknown{i}" for i in range(6)]
    analyze(bank)
    assert any(p["proposed"] == "1064.00" and p["support_count"] == 2 for p in bank.proposals)


def test_every_native_cell_has_a_real_source_box(bank):
    assert coverage(bank)["cells_with_source_boxes"] == coverage(bank)["cells"]
    source = bank.tables[0].cell_sources[10][5][0]
    assert source["text"] == "1081.00" and source["page"] == 1
    assert source["bbox"][2] > source["bbox"][0]
    assert source["confidence"] is None


def test_correction_preserves_source_and_invalidates_review(bank):
    reviewed = complete_review(bank, True, "Checked the source and acknowledged its wrong values.")
    assert review_current(reviewed)
    edited = apply_edit(
        reviewed,
        0,
        10,
        5,
        "1064.00",
        "Derived arithmetic correction; source still reads 1081.00.",
    )
    assert not review_current(edited)
    assert edited.tables[0].cell_sources[10][5][0]["text"] == "1081.00"
    assert bank.tables[0].rows[10][5] == "1081.00"
    assert not any(i.code == "running_balance" for i in edited.issues)
    assert history_valid(edited)


def test_tampered_data_invalidates_review(bank):
    reviewed = complete_review(bank, True, "Checked all source pages.")
    reviewed.tables[0].rows[0][5] = "999"
    assert not review_current(reviewed)


def test_header_edit_preserves_original_reading_and_resets_review(bank):
    reviewed = complete_review(bank, True, "Checked the source.")
    original = bank.tables[0].header_sources[0][0]["text"]
    edited = apply_edit(
        reviewed, 0, -1, 0, "Transaction reference", "Clearer label after source review."
    )
    assert edited.tables[0].headers[0] == "Transaction reference"
    assert edited.tables[0].header_sources[0][0]["text"] == original
    assert edited.history[-1]["row"] == -1 and not review_current(edited)


def test_tampered_history_is_rejected(bank):
    edited = apply_edit(bank, 0, 0, 2, "New note", "Checked source text.")
    edited.history[0]["after"] = "Different note"
    assert not history_valid(edited)
    with pytest.raises(ValueError, match="history"):
        apply_edit(edited, 0, 1, 2, "x", "Source checked.")


@pytest.mark.parametrize("checked,note", [(False, "Checked"), (True, "")])
def test_review_requires_explicit_source_attestation(bank, checked, note):
    with pytest.raises(ValueError):
        complete_review(bank, checked, note)


def test_audit_roundtrip_retains_boxes_scores_and_constraints(bank):
    bank.tables[0].cell_confidence[(0, 0)] = 0.72
    restored = Result.from_dict(json.loads(json.dumps(bank.to_dict())))
    assert restored.tables[0].cell_confidence[(0, 0)] == 0.72
    assert restored.tables[0].cell_sources == bank.tables[0].cell_sources
    assert restored.constraints == bank.constraints


def test_priority_review_queue_persists_cell_checks_without_changing_snapshot(bank):
    bank.tables[0].cell_confidence[(0, 0)] = 0.72
    queue = review_queue(bank)
    uncertain = next(item for item in queue["items"] if item["kind"] == "confidence")
    assert uncertain["table"] == 0 and uncertain["row"] == 0 and uncertain["column"] == 0
    assert uncertain["status"] == "pending" and queue["pending"] == queue["visible"]

    before = fingerprint(bank)
    checked = set_item_review(bank, uncertain["id"], True)
    updated = review_queue(checked)
    assert fingerprint(checked) == before
    assert (
        next(item for item in updated["items"] if item["id"] == uncertain["id"])["status"]
        == "checked"
    )
    assert updated["checked"] == 1

    reopened = set_item_review(checked, uncertain["id"], False)
    assert review_queue(reopened)["checked"] == 0
    with pytest.raises(ValueError, match="current extraction"):
        set_item_review(bank, "not-a-real-review-item", True)


def test_source_attestation_completes_visible_priority_queue(bank):
    bank.tables[0].cell_confidence[(0, 0)] = 0.72
    reviewed = complete_review(bank, True, "Checked every priority item against its source.")
    queue = review_queue(reviewed)
    assert queue["visible"] > 0 and queue["pending"] == 0
    assert queue["checked"] == queue["visible"] and review_current(reviewed)
    reopened = set_item_review(reviewed, queue["items"][0]["id"], False)
    assert not review_current(reopened)
    assert review_queue(reopened)["pending"] == 1


def test_workspace_baseline_is_immutable(bank, tmp_path):
    identifier, _ = create_job(
        "../../dummy.pdf", (tmp_path / "B_bank_errors.pdf").read_bytes(), tmp_path
    )
    save_result(identifier, bank, tmp_path)
    edited = apply_edit(bank, 0, 10, 5, "1064.00", "Arithmetic correction after source review.")
    save_result(identifier, edited, tmp_path)
    assert load_result(identifier, tmp_path).tables[0].rows[10][5] == "1064.00"
    assert load_result(identifier, tmp_path, baseline=True).tables[0].rows[10][5] == "1081.00"
    assert len(list(tmp_path.rglob("source.pdf"))) == 1


def test_corrupt_saved_payload_rejected(bank, tmp_path):
    identifier, _ = create_job("dummy.pdf", (tmp_path / "B_bank_errors.pdf").read_bytes(), tmp_path)
    save_result(identifier, bank, tmp_path)
    path = job_path(identifier, tmp_path) / "current.json"
    data = json.loads(path.read_text())
    data["result"]["tables"][0]["rows"][0][0] = "tampered"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="changed"):
        load_result(identifier, tmp_path)


def test_changed_original_source_rejected(bank, tmp_path):
    identifier, source = create_job(
        "dummy.pdf", (tmp_path / "B_bank_errors.pdf").read_bytes(), tmp_path
    )
    save_result(identifier, bank, tmp_path)
    source.write_bytes(b"changed source bytes")
    with pytest.raises(ValueError, match="source changed"):
        load_result(identifier, tmp_path)


@pytest.mark.parametrize("identifier", ["../outside", "C:/Windows", "a" * 31, "a" * 33])
def test_workspace_path_traversal_rejected(tmp_path, identifier):
    with pytest.raises(ValueError):
        job_path(identifier, tmp_path)


def test_verified_checkpoint_avoids_reextraction(tmp_path, monkeypatch):
    invoice_sample(tmp_path)
    source = tmp_path / "A_invoice_register.pdf"
    first = convert(source, checkpoint_dir=tmp_path / "cache")
    import truecell.pipeline as pipeline

    monkeypatch.setattr(
        pipeline,
        "extract_page",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not re-extract")),
    )
    second = convert(source, checkpoint_dir=tmp_path / "cache")
    assert second.tables[0].rows == first.tables[0].rows
    assert all(p.attempts[-1].strategy == "verified-resume" for p in second.pages)


def test_checkpoint_different_signature_recomputed(tmp_path):
    from truecell.models import PageReport

    cache = Checkpoints(tmp_path, "old")
    cache.save(1, [], PageReport(1, "empty"), [])
    assert Checkpoints(tmp_path, "new").load(1) is None
    (tmp_path / "page-001.json").write_text("{bad json")
    assert cache.load(1) is None


def test_export_contains_source_link_and_unreviewed_status(bank, tmp_path):
    from truecell.export import export_workbook

    path = export_workbook(bank, tmp_path / "proof.xlsx")
    workbook = load_workbook(path)
    assert workbook["Data 1"]["F12"].hyperlink.target.startswith("#'Cell Evidence'!")
    assert workbook["Verification"]["B4"].value == "Unreviewed"
    assert workbook["Repair Proposals"].max_row > 1
    assert not any(c.data_type == "f" for s in workbook for row in s for c in row)
