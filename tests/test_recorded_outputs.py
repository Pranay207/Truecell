import hashlib
import json

import pytest
from openpyxl import load_workbook

from scripts import verify_recorded_outputs
from truecell.export import export_workbook
from truecell.models import Result, Table


def _recorded_case(root):
    samples = root / "samples"
    outputs = root / "outputs"
    reports = root / "reports"
    samples.mkdir()
    outputs.mkdir()
    reports.mkdir()

    source = samples / "case.pdf"
    source.write_bytes(b"source document")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    truth = {
        "name": "case",
        "pages": 1,
        "tables": [{"headers": ["ID"], "rows": [["001"]]}],
    }
    (samples / "case.truth.json").write_text(json.dumps(truth), encoding="utf-8")
    result = Result(
        "case.pdf",
        tables=[Table(["ID"], [["001"]], 1, (0, 0, 1, 1), "native")],
        source_sha256=source_hash,
    )
    (outputs / "case.audit.json").write_text(json.dumps(result.to_dict()), encoding="utf-8")
    workbook = outputs / "case.xlsx"
    export_workbook(result, workbook)
    return workbook


def test_recorded_output_check_rejects_workbook_that_disagrees_with_audit(tmp_path, monkeypatch):
    workbook = _recorded_case(tmp_path)
    monkeypatch.setattr(verify_recorded_outputs, "ROOT", tmp_path)

    assert verify_recorded_outputs.main() == 0

    saved = load_workbook(workbook)
    try:
        saved["Data 1"]["A2"] = "999"
        saved.save(workbook)
    finally:
        saved.close()

    with pytest.raises(SystemExit, match="Workbook mismatch.*workbook values"):
        verify_recorded_outputs.main()
