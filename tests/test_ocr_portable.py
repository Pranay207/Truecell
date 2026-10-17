"""Portable OCR does not depend on software installed elsewhere on Windows."""

from truecell import ocr


def test_portable_mode_ignores_system_tesseract(monkeypatch):
    monkeypatch.setenv("TRUECELL_PORTABLE_RAPIDOCR_ONLY", "1")
    monkeypatch.setattr(ocr.shutil, "which", lambda _: "C:/Program Files/Tesseract/tesseract.exe")
    assert ocr.tesseract_path() is None
