"""Page profiling, language routing and automatic OCR escalation regressions."""

from dataclasses import replace

import fitz
import numpy as np
from PIL import Image, ImageDraw

from eval.score import score
from truecell.checkpoint import Checkpoints
from truecell.models import PageReport, Result, Table
from truecell.pipeline import convert
from truecell.profiling import detect_scripts, normalize_languages, profile_page
from truecell.router import route_page


def digital_table_pdf(path):
    with fitz.open() as document:
        page = document.new_page(width=500, height=500)
        page.insert_text((35, 35), "Invoice account amount total balance")
        for row in range(10):
            page.insert_text((40, 75 + row * 28), f"ITEM-{row:02d} Description {row} {row * 10}.00")
        for x in (30, 130, 330, 400, 470):
            page.draw_line((x, 55), (x, 370))
        for y in range(55, 371, 28):
            page.draw_line((30, y), (470, y))
        document.save(path)


def scanned_pdf(path):
    image = Image.new("RGB", (900, 600), "white")
    draw = ImageDraw.Draw(image)
    for y in range(60, 541, 60):
        draw.line((40, y, 860, y), fill="black", width=3)
    for x in (40, 240, 500, 680, 860):
        draw.line((x, 60, x, 540), fill="black", width=3)
    image_path = path.with_suffix(".png")
    image.save(image_path)
    with fitz.open() as document:
        page = document.new_page(width=450, height=300)
        page.insert_image(page.rect, filename=image_path)
        document.save(path)


def test_profiles_native_and_scanned_pages_and_records_routing(tmp_path):
    digital = tmp_path / "digital.pdf"
    scan = tmp_path / "scan.pdf"
    digital_table_pdf(digital)
    scanned_pdf(scan)
    with fitz.open(digital) as document:
        profile = profile_page(document[0])
        assert profile.content_mode == "digital"
        assert profile.native_text_health == "healthy"
        assert not profile.raster_profiled
        assert profile.table_likelihood >= 0.5
        assert profile.high_value_content
        assert route_page(document[0], profile) == "digital"
    with fitz.open(scan) as document:
        profile = profile_page(document[0])
        assert profile.content_mode == "scan"
        assert profile.native_text_health == "missing"
        assert profile.raster_profiled
        assert profile.image_coverage > 0.9
        assert profile.recommended_strategy == "ocr"
        assert route_page(document[0], profile) == "ocr"


def test_healthy_native_page_does_not_pay_for_raster_probe(tmp_path, monkeypatch):
    import truecell.profiling as profiling

    source = tmp_path / "digital.pdf"
    digital_table_pdf(source)
    monkeypatch.setattr(
        profiling,
        "_render_preview",
        lambda page: (_ for _ in ()).throw(AssertionError("unexpected rasterization")),
    )
    with fitz.open(source) as document:
        profile = profiling.profile_page(document[0])
    assert profile.content_mode == "digital"
    assert not profile.raster_profiled


def test_script_and_language_metadata_is_explicit():
    assert detect_scripts("Invoice వివరాలు कुल राशि") == ["Latin", "Devanagari", "Telugu"]
    assert normalize_languages("English, Telugu+hi") == ("eng", "tel", "hin")


def test_risky_native_page_automatically_gets_independent_ocr(tmp_path, monkeypatch):
    import truecell.ocr as ocr
    import truecell.pipeline as pipeline

    source = tmp_path / "native.pdf"
    digital_table_pdf(source)
    actual_profile = pipeline.profile_page

    def risky(page, languages):
        return replace(
            actual_profile(page, languages),
            native_text_health="marginal",
            cross_check_recommended=True,
            recommended_strategy="native-ocr-cross-check",
            risk_reasons=["marginal_native_text"],
        )

    native = Table(
        ["Item", "Description", "Qty", "Amount"],
        [["A", "Widget", "2", "10.00"], ["B", "Other", "3", "15.00"]],
        1,
        (30, 55, 470, 370),
        "native-lines",
    )
    checked = Table(native.headers[:], native.rows[:], 1, native.bbox, "ocr-test", confidence=0.98)
    monkeypatch.setattr(pipeline, "profile_page", risky)
    monkeypatch.setattr(pipeline, "extract_page", lambda *args: [native])
    monkeypatch.setattr(ocr, "available_engines", lambda: ["test"])
    monkeypatch.setattr(ocr, "extract_image", lambda *args, **kwargs: [checked])
    result = convert(source)
    attempts = result.pages[0].attempts
    assert any(attempt.engine == "native" for attempt in attempts)
    assert any(attempt.engine == "test" for attempt in attempts)
    assert result.pages[0].profile["cross_check_executed"] is True
    assert result.pages[0].profile["recommended_strategy"] == "native-ocr-cross-check"
    restored = Result.from_dict(result.to_dict())
    assert restored.pages[0].profile == result.pages[0].profile


def test_tesseract_receives_only_installed_requested_languages(monkeypatch):
    import pytesseract

    import truecell.ocr as ocr

    captured = {}
    monkeypatch.setattr(ocr, "tesseract_languages", lambda: ("eng", "hin", "tel"))
    monkeypatch.setattr(ocr, "tesseract_path", lambda: "tesseract")

    def fake_data(image, **options):
        captured.update(options)
        return {
            "left": [1],
            "top": [2],
            "width": [3],
            "height": [4],
            "text": ["నమస్తే"],
            "conf": [96],
        }

    monkeypatch.setattr(pytesseract, "image_to_data", fake_data)
    words = ocr.recognize(
        np.full((30, 80), 255, dtype=np.uint8),
        "tesseract",
        languages=("tel", "hin", "fra"),
    )
    assert captured["lang"] == "tel+hin"
    assert words[0]["text"] == "నమస్తే"


def test_page_profile_survives_verified_checkpoint(tmp_path):
    cache = Checkpoints(tmp_path / "cache", "profile-test")
    report = PageReport(
        1,
        "digital",
        profile={
            "content_mode": "digital",
            "quality_grade": "review",
            "risk_reasons": ["marginal_native_text"],
        },
    )
    cache.save(1, [], report, [])
    loaded = cache.load(1)
    assert loaded is not None
    assert loaded[1].profile == report.profile
    assert loaded[1].attempts[-1].strategy == "verified-resume"


def test_high_value_scan_uses_second_installed_engine(tmp_path, monkeypatch):
    import truecell.ocr as ocr

    source = tmp_path / "statement.png"
    Image.new("RGB", (300, 200), "white").save(source)
    calls = []

    def extract(image, page, engine, **options):
        calls.append(engine)
        return [
            Table(
                ["Account", "Debit", "Credit", "Balance"],
                [["001", "10.00", "", "90.00"], ["002", "", "5.00", "95.00"]],
                page,
                (0, 0, 100, 100),
                f"ocr-{engine}",
                0.99,
            )
        ]

    monkeypatch.setattr(ocr, "available_engines", lambda: ["first", "second"])
    monkeypatch.setattr(ocr, "extract_image", extract)
    result = convert(source)
    assert calls[:2] == ["first", "second"]
    assert result.pages[0].profile["high_value_detected_after_ocr"] is True
    assert any(
        attempt.strategy == "independent-language-aware-cross-check"
        for attempt in result.pages[0].attempts
    )


def test_missing_requested_language_pack_is_audited(tmp_path, monkeypatch):
    import truecell.ocr as ocr

    source = tmp_path / "telugu.png"
    Image.new("RGB", (300, 200), "white").save(source)
    table = Table(["Name", "Value"], [["Sample", "1"]], 1, (0, 0, 100, 100), "ocr-rapidocr")
    monkeypatch.setattr(ocr, "available_engines", lambda: ["rapidocr"])
    monkeypatch.setattr(ocr, "extract_image", lambda *args, **kwargs: [table])
    result = convert(source, ocr_languages="tel")
    assert result.pages[0].profile["requested_ocr_languages"] == ["tel"]
    assert result.pages[0].profile["ocr_engine_language_coverage"] == {"rapidocr": []}
    assert any(issue.code == "ocr_language_unavailable" for issue in result.issues)


def test_no_recovery_keeps_scanned_page_to_one_engine(tmp_path, monkeypatch):
    import truecell.ocr as ocr

    source = tmp_path / "statement.png"
    Image.new("RGB", (300, 200), "white").save(source)
    calls = []

    def extract(image, page, engine, **options):
        calls.append(engine)
        return [
            Table(
                ["Account", "Balance"],
                [["001", "90.00"]],
                page,
                (0, 0, 100, 100),
                f"ocr-{engine}",
                0.99,
            )
        ]

    monkeypatch.setattr(ocr, "available_engines", lambda: ["first", "second"])
    monkeypatch.setattr(ocr, "extract_image", extract)
    result = convert(source, recover=False)
    assert calls == ["first"]
    assert len(result.pages[0].attempts) == 1


def test_headerless_native_cross_check_is_bounded(monkeypatch):
    import json

    import truecell.ocr as ocr

    calls = []

    def empty_cross_check(image, page, engine, **options):
        calls.append((page, engine, options))
        return []

    monkeypatch.setattr(ocr, "available_engines", lambda: ["first", "second"])
    monkeypatch.setattr(ocr, "extract_image", empty_cross_check)
    source = "samples/D_headerless.pdf"
    result = convert(source)
    truth = json.loads(open("samples/D_headerless.truth.json", encoding="utf-8").read())
    assert score(truth, result)["pass"]
    assert [page_number for page_number, _engine, _options in calls] == [2, 3]
    assert all(engine == "first" and not options for _, engine, options in calls)
    assert all(page.profile["native_candidate_available"] for page in result.pages)
    forbidden = ("threshold-", "cell-recheck-", "perspective-", "rotate-")
    assert not any(
        attempt.strategy.startswith(forbidden) for page in result.pages for attempt in page.attempts
    )
