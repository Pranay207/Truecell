import json
from pathlib import Path

import fitz

from eval.generate_equivalent import SCHEMAS, write_fixture
from eval.score import score
from truecell.models import Result

ROOT = Path(__file__).resolve().parents[1]


def test_thirteen_page_equivalent_is_deterministic_and_fully_truth_bound(tmp_path):
    write_fixture(tmp_path)
    source = tmp_path / "G_thirteen_page_equivalent.pdf"
    truth = json.loads((tmp_path / "G_thirteen_page_equivalent.truth.json").read_text())
    with fitz.open(source) as document:
        assert len(document) == 13
    assert truth["pages"] == 13
    assert len(truth["tables"]) == 4
    assert all(len(table["headers"]) == 14 for table in truth["tables"])
    assert [table["headers"] for table in truth["tables"]] == [item[1] for item in SCHEMAS]
    assert sum(len(table["rows"]) for table in truth["tables"]) == 78
    assert (tmp_path / "G_thirteen_page_equivalent.truth.xlsx").is_file()


def test_verified_thirteen_page_audit_matches_every_truth_cell():
    truth = json.loads(
        (ROOT / "samples" / "G_thirteen_page_equivalent.truth.json").read_text(encoding="utf-8")
    )
    result = Result.from_dict(
        json.loads(
            (ROOT / "outputs" / "G_thirteen_page_equivalent.audit.json").read_text(encoding="utf-8")
        )
    )
    metric = score(truth, result)
    assert metric["tables_count_match"]
    assert metric["shape_match"]
    assert metric["header_match"] == 1
    assert metric["row_match"] == 1
    assert metric["cell_exact"] == 1
    assert metric["expected_cells"] == 1092
