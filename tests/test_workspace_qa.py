"""Damaged saved-job metadata cannot break other workspaces or startup."""

import hashlib
import json

import pytest

from truecell import workspace
from truecell.models import PageReport, Result
from truecell.workspace import atomic_json, create_job, job_path, list_jobs, save_result


@pytest.mark.parametrize(
    "bad",
    [
        {"created": None},
        {"created": "not-a-date"},
        {"name": None},
        {"status": "unexpected"},
        {"source": "../outside.pdf"},
        {"options": []},
    ],
)
def test_corrupt_job_metadata_does_not_hide_valid_job(tmp_path, bad):
    valid, _ = create_job("valid.pdf", b"source", tmp_path)
    broken, _ = create_job("broken.pdf", b"source", tmp_path)
    path = job_path(broken, tmp_path) / "metadata.json"
    record = json.loads(path.read_text())
    record.update(bad)
    path.write_text(json.dumps(record))
    assert [job["id"] for job in list_jobs(tmp_path)] == [valid]


@pytest.mark.parametrize("missing", ["created", "name", "status", "source"])
def test_missing_job_fields_are_isolated(tmp_path, missing):
    valid, _ = create_job("valid.pdf", b"source", tmp_path)
    broken, _ = create_job("broken.pdf", b"source", tmp_path)
    path = job_path(broken, tmp_path) / "metadata.json"
    record = json.loads(path.read_text())
    del record[missing]
    path.write_text(json.dumps(record))
    assert [job["id"] for job in list_jobs(tmp_path)] == [valid]


def test_metadata_cannot_point_to_another_workspace(tmp_path):
    valid, _ = create_job("valid.pdf", b"source", tmp_path)
    broken, _ = create_job("broken.pdf", b"source", tmp_path)
    path = job_path(broken, tmp_path) / "metadata.json"
    record = json.loads(path.read_text())
    record["id"] = valid
    path.write_text(json.dumps(record))
    assert [job["id"] for job in list_jobs(tmp_path)] == [valid]


def test_partial_extraction_remains_resumable(tmp_path):
    identifier, _ = create_job("dummy.pdf", b"source", tmp_path)
    result = Result(
        "dummy.pdf",
        source_sha256=hashlib.sha256(b"source").hexdigest(),
        pages=[PageReport(1, "ocr", error="Temporary OCR failure")],
    )
    save_result(identifier, result, tmp_path)
    assert list_jobs(tmp_path)[0]["status"] == "partial"


def test_atomic_json_retries_a_transient_windows_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "metadata.json"
    actual_replace = workspace.os.replace
    calls = []
    delays = []

    def flaky_replace(source, destination):
        calls.append((source, destination))
        if len(calls) < 3:
            raise PermissionError("temporary sharing violation")
        actual_replace(source, destination)

    monkeypatch.setattr(workspace.os, "replace", flaky_replace)
    monkeypatch.setattr(workspace.time, "sleep", delays.append)

    atomic_json(target, {"status": "ready"})

    assert json.loads(target.read_text()) == {"status": "ready"}
    assert len(calls) == 3
    assert delays == [0.02, 0.04]
