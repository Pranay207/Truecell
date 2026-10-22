"""Checkpoint identity must include every active OCR language asset."""

from __future__ import annotations

from types import SimpleNamespace

from truecell.checkpoint import signature


def test_requested_language_asset_change_invalidates_checkpoint(tmp_path, monkeypatch):
    binary = tmp_path / "tesseract.exe"
    binary.write_bytes(b"test binary")
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "tel.traineddata").write_bytes(b"telugu-pack-v1")
    (tessdata / "osd.traineddata").write_bytes(b"orientation-pack")

    monkeypatch.setattr("truecell.ocr.tesseract_path", lambda: str(binary))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="tesseract 5.test\n"),
    )

    first = signature("a" * 64, {"ocr_languages": "tel"})
    (tessdata / "tel.traineddata").write_bytes(b"telugu-pack-v2")
    second = signature("a" * 64, {"ocr_languages": "tel"})

    assert first != second
