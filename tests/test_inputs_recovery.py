"""Input bounds, page failure containment and optional-model shape validation."""

import fitz
import pytest
from PIL import Image

from eval.generate_samples import invoice_sample
from eval.score import score
from truecell.llm_repair import configured, validate_payload
from truecell.models import Result, Table
from truecell.pipeline import convert
from truecell.recover import evaluate
from truecell.router import InputError, open_document, route_page


def test_fifty_page_limit(tmp_path):
    source = tmp_path / "too_many.pdf"
    with fitz.open() as document:
        for _ in range(51):
            document.new_page()
        document.save(source)
    with pytest.raises(InputError, match="maximum is 50"):
        with open_document(source):
            pass


def test_encrypted_pdf(tmp_path):
    source = tmp_path / "locked.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(
            source,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="secret",
            owner_pw="owner",
        )
    with pytest.raises(InputError, match="Encrypted"):
        with open_document(source):
            pass


def test_corrupt_pdf(tmp_path):
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"not a PDF")
    with pytest.raises(InputError, match="Cannot open"):
        with open_document(source):
            pass


def test_unsupported_input(tmp_path):
    source = tmp_path / "file.txt"
    source.write_text("data")
    with pytest.raises(InputError, match="Use a PDF"):
        with open_document(source):
            pass


def test_multipage_tiff(tmp_path):
    source = tmp_path / "frames.tiff"
    a, b = Image.new("RGB", (200, 100), "white"), Image.new("RGB", (200, 100), "gray")
    a.save(source, save_all=True, append_images=[b])
    with open_document(source) as document:
        assert len(document) == 2
        assert route_page(document[0]) == "ocr"


def test_blank_page_reported_not_crash(tmp_path):
    source = tmp_path / "blank.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(source)
    result = convert(source, tmp_path / "blank.xlsx")
    assert result.pages[0].route == "empty"
    assert result.issues[0].code == "empty_page"


def test_page_failure_continues(monkeypatch, tmp_path):
    import truecell.pipeline as pipeline

    invoice_sample(tmp_path)
    original = pipeline.extract_page

    def broken(page, number, strategy):
        if number == 2:
            raise RuntimeError("deliberate extraction failure")
        return original(page, number, strategy)

    monkeypatch.setattr(pipeline, "extract_page", broken)
    # Disable OCR availability to ensure the failed native page has a clear failure record.
    import truecell.ocr as ocr

    monkeypatch.setattr(ocr, "available_engines", lambda: [])
    result = convert(tmp_path / "A_invoice_register.pdf")
    assert len(result.pages) == 3
    assert any(i.page == 2 and i.code == "page_failed" for i in result.issues)
    assert sum(len(t.rows) for t in result.tables) == 32


def test_no_network_without_configuration(monkeypatch):
    monkeypatch.delenv("TRUECELL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("TRUECELL_LLM_MODEL", raising=False)
    assert not configured()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tables": "bad"},
        {"tables": [{"headers": ["A", "B"], "rows": [["1"]]}]},
        {"tables": [{"headers": ["A"], "rows": []}]},
        {"tables": [], "extra": True},
        {"tables": [{"headers": ["A", "B"], "rows": [[1, 2]]}]},
    ],
)
def test_vision_invalid_payload_rejected(payload):
    with pytest.raises(ValueError):
        validate_payload(payload)


def test_vision_payload_valid():
    data = {"tables": [{"headers": ["A", "B"], "rows": [["001", "10.00"]]}]}
    assert validate_payload(data) == data["tables"]


def test_empty_candidate_never_beats_nonempty():
    t = Table(["A", "B"], [["x", "1"]], 1, (0, 0, 10, 10), "native")
    assert evaluate([t])[0] > evaluate([])[0]


def test_false_column_splits_do_not_earn_more_coverage():
    good = Table(
        ["Code", "Description", "Units"],
        [["A", "Widget model 1", "2"], ["B", "Widget model 2", "3"]],
        1,
        (0, 0, 10, 10),
        "native-words",
        0.72,
    )
    bad = Table(
        ["Code", "Description", "Column 3", "Column 4", "Units"],
        [["A", "Widget", "model", "1", "2"], ["B", "Widget", "model", "2", "3"]],
        1,
        (0, 0, 10, 10),
        "native-text",
        0.82,
    )
    assert evaluate([good])[0] > evaluate([bad])[0]


def test_scorer_penalizes_extra_table():
    t = Table(["ID", "Amt"], [["A", "1"]], 1, (0, 0, 10, 10), "native")
    truth = {
        "name": "test",
        "pages": 1,
        "tables": [{"headers": t.headers, "rows": t.rows}],
    }
    result = score(truth, Result("dummy", [t, t]))
    assert result["precision"] == 0.5
    assert not result["pass"] and not result["tables_count_match"]


def test_scorer_counts_duplicate_multiplicity():
    t = Table(["ID", "Amt"], [["A", "1"]], 1, (0, 0, 10, 10), "native")
    truth = {
        "name": "test",
        "pages": 1,
        "tables": [{"headers": t.headers, "rows": [["A", "1"], ["A", "1"]]}],
    }
    result = score(truth, Result("dummy", [t]))
    assert result["row_match"] == 0.5 and not result["pass"]
