"""Command-line option forwarding and help regressions."""

import pytest

from truecell import cli
from truecell.models import Result, Table


def successful_result(source):
    table = Table(["Name", "Value"], [["Sample", "1"]], 1, (0, 0, 10, 10), "test")
    return Result(str(source), [table])


def test_cli_forwards_normalized_multilingual_ocr_option(tmp_path, monkeypatch, capsys):
    captured = {}

    def fake_convert(source, output, **options):
        captured.update(source=source, output=output, options=options)
        return successful_result(source)

    monkeypatch.setattr(cli, "convert", fake_convert)
    source = tmp_path / "source.pdf"
    output = tmp_path / "result.xlsx"
    assert cli.main([str(source), "-o", str(output), "--ocr-languages", "English+Telugu,hi"]) == 0
    assert captured["options"]["ocr_languages"] == ("eng", "tel", "hin")
    assert "Saved" in capsys.readouterr().out


def test_cli_leaves_environment_fallback_to_pipeline(tmp_path, monkeypatch):
    captured = {}

    def fake_convert(source, output, **options):
        captured.update(options)
        return successful_result(source)

    monkeypatch.setattr(cli, "convert", fake_convert)
    source = tmp_path / "source.pdf"
    assert cli.main([str(source)]) == 0
    assert captured["ocr_languages"] is None


def test_cli_help_documents_language_examples(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--help"])
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "--ocr-languages" in help_text
    assert "eng+tel" in help_text
    assert "TRUECELL_OCR_LANGUAGES" in help_text


def test_cli_rejects_invalid_language_code(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["source.pdf", "--ocr-languages", "../../bad"])
    assert stopped.value.code == 2
    assert "Invalid OCR language code" in capsys.readouterr().err
