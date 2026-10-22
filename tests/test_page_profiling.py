"""Page profiling, language routing and automatic OCR escalation regressions."""

from dataclasses import replace
from threading import Barrier
from time import sleep

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


def test_native_fallback_candidates_run_in_bounded_parallel_plan_order(tmp_path, monkeypatch):
    import truecell.pipeline as pipeline

    source = tmp_path / "native.pdf"
    digital_table_pdf(source)
    meeting = Barrier(2, timeout=3)

    def extract(_page, number, strategy):
        if strategy == "lines":
            return []
        meeting.wait()
        if strategy == "text":
            sleep(0.03)  # Completion order must not change the recorded plan order.
        return [
            Table(
                ["Code", "Description", "Units"],
                [["A", "Widget", "2"], ["B", "Other", "3"]],
                number,
                (0, 0, 100, 100),
                f"native-{strategy}",
                0.99,
            )
        ]

    monkeypatch.setattr(pipeline, "extract_page", extract)
    result = convert(source)
    attempts = result.pages[0].attempts
    assert [attempt.strategy for attempt in attempts[:3]] == ["lines", "text", "words"]
    assert [attempt.execution for attempt in attempts[1:3]] == [
        "bounded-parallel",
        "bounded-parallel",
    ]
    batch = result.pages[0].profile["parallel_candidate_batches"][0]
    assert batch["workers"] == 2
    assert batch["candidate_ids"] == [attempts[1].candidate_id, attempts[2].candidate_id]
    assert result.pages[0].profile["candidate_policy"] == {
        "max_workers": 2,
        "parallel_scope": "independent-candidates-only",
        "dependent_recovery": "sequential",
        "tie_breaker": "declared-plan-order",
    }
    assert next(attempt for attempt in attempts if attempt.selected).rank == 1


def test_two_safe_ocr_engines_run_in_parallel_and_selection_is_audited(tmp_path, monkeypatch):
    import truecell.ocr as ocr

    source = tmp_path / "scan.png"
    Image.new("RGB", (300, 200), "white").save(source)
    meeting = Barrier(2, timeout=3)

    def unused_adapter(_gray, _languages):
        return []

    def extract(_image, page, engine, **_options):
        meeting.wait()
        if engine == "alpha":
            sleep(0.03)
        rows = [["A", "1"], ["B", "2"]]
        return [Table(["Code", "Amount"], rows, page, (0, 0, 100, 100), f"ocr-{engine}", 0.99)]

    ocr.register_ocr_adapter("alpha", unused_adapter, parallel_safe=True)
    ocr.register_ocr_adapter("beta", unused_adapter, parallel_safe=True)
    try:
        monkeypatch.setattr(ocr, "available_engines", lambda: ["alpha", "beta"])
        monkeypatch.setattr(ocr, "extract_image", extract)
        result = convert(source, verify=True)
    finally:
        ocr.unregister_ocr_adapter("alpha")
        ocr.unregister_ocr_adapter("beta")

    attempts = result.pages[0].attempts
    assert [attempt.engine for attempt in attempts[:2]] == ["alpha", "beta"]
    assert all(attempt.execution == "bounded-parallel" for attempt in attempts[:2])
    selected = next(attempt for attempt in attempts if attempt.selected)
    # Exact ties use declared plan order, not nondeterministic completion order.
    assert selected.engine == "alpha"
    assert selected.rank == 1
    assert selected.selection_reason.startswith("Highest deterministic candidate key")
    assert result.pages[0].profile["candidate_selection"]["candidate_id"] == selected.candidate_id
    assert Result.from_dict(result.to_dict()).pages[0].attempts[1].candidate_id


def test_optional_layout_adapter_capability_is_honest_and_word_records_are_checked(monkeypatch):
    import truecell.ocr as ocr

    monkeypatch.setattr(ocr, "_module_available", lambda name: name in {"paddleocr", "paddle"})
    unavailable = ocr.engine_capabilities("eng+tel")["paddleocr"]
    assert unavailable["installed"] is True
    assert unavailable["available"] is False
    assert "no local Truecell adapter" in unavailable["reason"]

    seen = []

    def recognize(_gray, languages):
        seen.append(languages)
        return [
            {
                "x0": 1,
                "x1": 8,
                "top": 2,
                "bottom": 9,
                "text": " నమస్తే ",
                "confidence": 1.4,
            }
        ]

    ocr.register_ocr_adapter(
        "paddleocr",
        recognize,
        languages=("eng", "tel"),
        provider="local-paddle-layout",
        layout_aware=True,
        parallel_safe=False,
    )
    try:
        capability = ocr.engine_capabilities("eng+tel")["paddleocr"]
        assert "paddleocr" in ocr.available_engines()
        words = ocr.recognize(np.full((20, 20), 255, dtype=np.uint8), "paddleocr", languages="tel")
    finally:
        ocr.unregister_ocr_adapter("paddleocr")
    assert capability["available"] is True and capability["layout_aware"] is True
    assert capability["requested_language_coverage"] == ["eng", "tel"]
    assert seen == [("tel",)]
    assert words[0]["text"] == "నమస్తే"
    assert words[0]["confidence"] == 1.0


def test_rapidocr_capability_requires_the_verified_local_model(monkeypatch):
    import truecell.ocr as ocr

    monkeypatch.setattr(ocr, "_module_available", lambda name: name == "rapidocr_onnxruntime")
    monkeypatch.setattr(ocr, "rapid_model_status", lambda: (False, "model checksum mismatch"))
    capability = ocr.engine_capabilities()["rapidocr"]
    assert capability["installed"] is True
    assert capability["available"] is False
    assert capability["reason"] == "model checksum mismatch"
