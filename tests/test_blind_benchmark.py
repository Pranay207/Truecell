import hashlib
import json

import pytest

from eval.benchmark import ManifestError, load_manifest, score_saved
from truecell.models import Result, Table


def write_manifest(path, cases):
    path.write_text(json.dumps({"version": 1, "suite": "holdout", "cases": cases}))


def test_manifest_rejects_duplicates_and_unsafe_paths(tmp_path):
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

    write_manifest(
        manifest,
        [{"id": "case", "file": "../private.pdf", "sha256": digest}],
    )
    loaded = load_manifest(manifest)
    # Path containment is checked when a pack is actually used.
    from eval.benchmark import _relative

    with pytest.raises(ManifestError, match="inside"):
        _relative(tmp_path, loaded["cases"][0]["file"])


def test_saved_audit_is_scored_without_reextracting(tmp_path):
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
    (output / "case-1.audit.json").write_text(json.dumps(result.to_dict()))
    (output / "run.json").write_text(
        json.dumps(
            {
                "suite": "holdout",
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "truth_available_during_extraction": False,
                "cases": [
                    {
                        "id": "case-1",
                        "source_sha256": source_hash,
                        "audit": "case-1.audit.json",
                    }
                ],
            }
        )
    )
    (truth_root / "case-1.truth.json").write_text(
        json.dumps(
            {
                "name": "case-1",
                "pages": 1,
                "tables": [{"headers": ["ID", "Amount"], "rows": [["001", "10.00"]]}],
            }
        )
    )
    metrics = score_saved(manifest, output, truth_root)
    assert metrics[0]["pass"] is True
    assert (output / "RESULTS.md").is_file()


def test_scoring_refuses_manifest_changed_after_extraction(tmp_path):
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, [])
    output = tmp_path / "run"
    output.mkdir()
    (output / "run.json").write_text(json.dumps({"manifest_sha256": "wrong", "cases": []}))
    with pytest.raises(ManifestError, match="changed"):
        score_saved(manifest, output, tmp_path)
