import hashlib
import json
import shutil
from pathlib import Path

import pytest

from eval.benchmark import (
    RUN_VERSION,
    ManifestError,
    extract_manifest,
    load_manifest,
    score_saved,
    sha256,
    source_fingerprint,
)
from truecell.export import export_workbook
from truecell.models import Result, Table

ROOT = Path(__file__).resolve().parents[1]


def write_manifest(path, cases):
    path.write_text(json.dumps({"version": 1, "suite": "holdout", "cases": cases}))


def write_run(output, manifest, result, identifier="case-1", ocr_languages=None):
    audit_path = output / f"{identifier}.audit.json"
    workbook_path = output / f"{identifier}.xlsx"
    audit_path.write_text(json.dumps(result.to_dict()))
    export_workbook(result, workbook_path)
    run = {
        "run_version": RUN_VERSION,
        "suite": "holdout",
        "manifest_sha256": sha256(manifest),
        "extractor_fingerprint": source_fingerprint(),
        "truth_available_during_extraction": False,
        "truth_protocol": "evaluator-withheld",
        "cases": [
            {
                "id": identifier,
                "source_sha256": result.source_sha256,
                "ocr_languages": ocr_languages or ["eng"],
                "extraction_signature": "1" * 64,
                "audit": audit_path.name,
                "audit_sha256": sha256(audit_path),
                "workbook": workbook_path.name,
                "workbook_sha256": sha256(workbook_path),
            }
        ],
    }
    run_path = output / "run.json"
    run_path.write_text(json.dumps(run))
    return run_path, audit_path, workbook_path


def test_manifest_rejects_duplicates_unsafe_paths_and_bad_languages(tmp_path):
    digest = "0" * 64
    manifest = tmp_path / "manifest.json"
    write_manifest(
        manifest,
        [
            {"id": "same", "file": "one.pdf", "sha256": digest},
            {"id": "same", "file": "two.pdf", "sha256": digest},
        ],
    )
    with pytest.raises(ManifestError, match="Duplicate"):
        load_manifest(manifest)

    write_manifest(manifest, [{"id": "case", "file": "../private.pdf", "sha256": digest}])
    loaded = load_manifest(manifest)
    from eval.benchmark import _relative

    with pytest.raises(ManifestError, match="inside"):
        _relative(tmp_path, loaded["cases"][0]["file"])

    write_manifest(
        manifest,
        [{"id": "case", "file": "case.pdf", "sha256": digest, "ocr_languages": "bad!"}],
    )
    with pytest.raises(ManifestError, match="OCR languages"):
        load_manifest(manifest)


def test_saved_audit_and_matching_workbook_are_scored_without_reextracting(tmp_path):
    source_hash = hashlib.sha256(b"held-out-source").hexdigest()
    manifest = tmp_path / "manifest.json"
    write_manifest(
        manifest,
        [
            {
                "id": "case-1",
                "file": "case-1.pdf",
                "sha256": source_hash,
                "truth": "case-1.truth.json",
                "category": "register",
                "language": "English",
            }
        ],
    )
    output = tmp_path / "run"
    truth_root = tmp_path / "truth"
    output.mkdir()
    truth_root.mkdir()
    result = Result(
        "case-1.pdf",
        tables=[Table(["ID", "Amount"], [["001", "10.00"]], 1, (0, 0, 1, 1), "native")],
        source_sha256=source_hash,
    )
    run_path, _, _ = write_run(output, manifest, result)
    (truth_root / "case-1.truth.json").write_text(
        json.dumps(
            {
                "name": "case-1",
                "pages": 1,
                "tables": [{"headers": ["ID", "Amount"], "rows": [["001", "10.00"]]}],
            }
        )
    )

    metrics = score_saved(manifest, output, truth_root, sha256(run_path))
    assert metrics[0]["pass"] is True
    assert metrics[0]["extractor_fingerprint"] == source_fingerprint()
    assert metrics[0]["extraction_signature"] == "1" * 64
    assert (output / "RESULTS.md").is_file()


def test_scoring_refuses_changed_saved_artifacts(tmp_path):
    source_hash = hashlib.sha256(b"held-out-source").hexdigest()
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, [{"id": "case-1", "file": "case-1.pdf", "sha256": source_hash}])
    output = tmp_path / "run"
    truth_root = tmp_path / "truth"
    output.mkdir()
    truth_root.mkdir()
    result = Result("case-1.pdf", source_sha256=source_hash)
    run_path, audit_path, _ = write_run(output, manifest, result)
    (truth_root / "case-1.truth.json").write_text(
        json.dumps({"name": "case-1", "pages": 1, "tables": []})
    )
    seal = sha256(run_path)
    audit_path.write_text("{}")

    with pytest.raises(ManifestError, match="audit was changed"):
        score_saved(manifest, output, truth_root, seal)


def test_scoring_refuses_manifest_or_run_changed_after_extraction(tmp_path):
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, [])
    output = tmp_path / "run"
    output.mkdir()
    run_path = output / "run.json"
    run_path.write_text(
        json.dumps(
            {
                "run_version": RUN_VERSION,
                "manifest_sha256": "wrong",
                "extractor_fingerprint": source_fingerprint(),
                "truth_available_during_extraction": False,
                "truth_protocol": "evaluator-withheld",
                "cases": [],
            }
        )
    )
    seal = sha256(run_path)
    with pytest.raises(ManifestError, match="Manifest changed"):
        score_saved(manifest, output, tmp_path, seal)

    run_path.write_text(run_path.read_text() + " ")
    with pytest.raises(ManifestError, match="run.json changed"):
        score_saved(manifest, output, tmp_path, seal)


@pytest.mark.parametrize(
    "payload,reason",
    [
        ("not-json", "Cannot read"),
        (json.dumps([]), "root must be an object"),
        (
            json.dumps(
                {
                    "run_version": RUN_VERSION,
                    "manifest_sha256": "unused",
                    "extractor_fingerprint": source_fingerprint(),
                    "truth_available_during_extraction": False,
                    "truth_protocol": "evaluator-withheld",
                    "cases": [{"id": []}],
                }
            ),
            "invalid case id",
        ),
    ],
)
def test_scoring_rejects_malformed_sealed_run_as_manifest_error(tmp_path, payload, reason):
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, [])
    if reason == "invalid case id":
        run = json.loads(payload)
        run["manifest_sha256"] = sha256(manifest)
        payload = json.dumps(run)
    output = tmp_path / "run"
    output.mkdir()
    run_path = output / "run.json"
    run_path.write_text(payload)

    with pytest.raises(ManifestError, match=reason):
        score_saved(manifest, output, tmp_path, sha256(run_path))


def test_source_fingerprint_includes_bundled_ocr_models(tmp_path):
    for folder in ("truecell", "eval", "models", "frontend"):
        (tmp_path / folder).mkdir()
    (tmp_path / "truecell" / "engine.py").write_text("engine = 1")
    (tmp_path / "eval" / "score.py").write_text("score = 1")
    model = tmp_path / "models" / "recognizer.onnx"
    model.write_bytes(b"model-v1")
    (tmp_path / "requirements.txt").write_text("example==1")
    (tmp_path / "frontend" / "package-lock.json").write_text("{}")

    first = source_fingerprint(tmp_path)
    model.write_bytes(b"model-v2")

    assert source_fingerprint(tmp_path) != first


def test_scoring_refuses_correctly_hashed_workbook_that_disagrees_with_audit(tmp_path):
    source_hash = hashlib.sha256(b"held-out-source").hexdigest()
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, [{"id": "case-1", "file": "case.pdf", "sha256": source_hash}])
    output = tmp_path / "run"
    truth_root = tmp_path / "truth"
    output.mkdir()
    truth_root.mkdir()
    result = Result(
        "case.pdf",
        tables=[Table(["ID"], [["001"]], 1, (0, 0, 1, 1), "native")],
        source_sha256=source_hash,
    )
    run_path, _, workbook_path = write_run(output, manifest, result)
    wrong = Result(
        "case.pdf",
        tables=[Table(["ID"], [["999"]], 1, (0, 0, 1, 1), "native")],
        source_sha256=source_hash,
    )
    export_workbook(wrong, workbook_path)
    run = json.loads(run_path.read_text())
    run["cases"][0]["workbook_sha256"] = sha256(workbook_path)
    run_path.write_text(json.dumps(run))
    seal = sha256(run_path)
    (truth_root / "case-1.truth.json").write_text(
        json.dumps(
            {
                "name": "case-1",
                "pages": 1,
                "tables": [{"headers": ["ID"], "rows": [["001"]]}],
            }
        )
    )

    with pytest.raises(ManifestError, match="workbook values"):
        score_saved(manifest, output, truth_root, seal)


def test_two_stage_blind_workflow_extracts_before_truth_is_supplied(tmp_path):
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    truth_root = tmp_path / "withheld-truth"
    inputs.mkdir()
    source = inputs / "invoice.pdf"
    shutil.copy2(ROOT / "samples" / "A_invoice_register.pdf", source)
    manifest = tmp_path / "manifest.json"
    write_manifest(
        manifest,
        [
            {
                "id": "invoice",
                "file": source.name,
                "sha256": sha256(source),
                "truth": "invoice.truth.json",
                "category": "invoice",
                "language": "English",
                "ocr_languages": ["English", "Telugu"],
            }
        ],
    )

    assert not truth_root.exists()
    run = extract_manifest(manifest, inputs, outputs)
    run_path = outputs / "run.json"
    seal = sha256(run_path)
    assert run["run_version"] == RUN_VERSION
    assert run["truth_available_during_extraction"] is False
    assert run["truth_protocol"] == "evaluator-withheld"
    assert run["cases"][0]["ocr_languages"] == ["eng", "tel"]
    assert run["cases"][0]["audit_sha256"] == sha256(outputs / "invoice.audit.json")
    assert run["cases"][0]["workbook_sha256"] == sha256(outputs / "invoice.xlsx")

    truth_root.mkdir()
    shutil.copy2(
        ROOT / "samples" / "A_invoice_register.truth.json",
        truth_root / "invoice.truth.json",
    )
    metrics = score_saved(manifest, outputs, truth_root, seal)
    assert metrics[0]["pass"] is True
    assert metrics[0]["truth_sha256"] == sha256(truth_root / "invoice.truth.json")
