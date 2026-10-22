"""Reuse completed pages only when source, extraction code and runtime agree."""

from __future__ import annotations

import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .models import Attempt, Issue, PageReport, Table
from .review import digest
from .workspace import atomic_json


def source_hash(path: str | Path) -> str:
    """Hash a source with bounded read buffers."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def signature(source_sha256: str, options: dict) -> str:
    """Fingerprint local extraction implementation and pinned runtime versions."""
    code = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        code.update(path.name.encode())
        code.update(path.read_bytes())
    assets = {}
    for path in sorted((Path(__file__).resolve().parents[1] / "models").glob("*.onnx")):
        assets[path.name] = source_hash(path)
    import importlib.util

    spec = importlib.util.find_spec("rapidocr_onnxruntime")
    if spec and spec.origin:
        for path in sorted((Path(spec.origin).parent / "models").glob("*.onnx")):
            assets["rapidocr/" + path.name] = source_hash(path)
    import subprocess

    from .ocr import available_engines, tesseract_path
    from .profiling import normalize_languages

    ocr_version = ""
    binary = tesseract_path()
    if binary:
        import os

        directories = [
            Path(binary).parent / "tessdata",
            Path("/usr/share/tesseract-ocr/5/tessdata"),
        ]
        if os.getenv("TESSDATA_PREFIX"):
            directories.insert(0, Path(os.environ["TESSDATA_PREFIX"]))
        requested_languages = normalize_languages(options.get("ocr_languages"))
        traineddata = [f"{language}.traineddata" for language in requested_languages]
        traineddata.append("osd.traineddata")
        for folder in directories:
            for name in dict.fromkeys(traineddata):
                if (folder / name).is_file():
                    assets["tesseract/" + str(folder / name)] = source_hash(folder / name)
        try:
            ocr_version = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=5
            ).stdout.splitlines()[0]
        except (OSError, subprocess.TimeoutExpired, IndexError):
            ocr_version = "unavailable"
    import os

    if options.get("allow_cloud"):
        options = {
            **options,
            "model": os.getenv("TRUECELL_LLM_MODEL", ""),
            "endpoint": os.getenv("TRUECELL_LLM_ENDPOINT", ""),
        }
    packages = {}
    for name in [
        "PyMuPDF",
        "pdfplumber",
        "rapidocr-onnxruntime",
        "onnxruntime",
        "pytesseract",
        "opencv-python",
    ]:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "not installed"
    return digest(
        {
            "source": source_sha256,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "code": code.hexdigest(),
            "packages": packages,
            "options": options,
            "assets": assets,
            "ocr_engines": available_engines(),
            "tesseract_version": ocr_version,
        }
    )


class Checkpoints:
    """Atomic page records, never trusted executable state or pickle files."""

    def __init__(self, folder: Path, identity: str):
        self.folder = folder
        self.identity = identity
        folder.mkdir(parents=True, exist_ok=True)

    def load(self, page: int) -> tuple[list[Table], PageReport, list[Issue]] | None:
        """Return a validated complete page or recompute on any mismatch."""
        try:
            record = json.loads((self.folder / f"page-{page:03d}.json").read_text(encoding="utf-8"))
            payload = record["payload"]
            if record["identity"] != self.identity or record["sha256"] != digest(payload):
                return None
            metadata = payload["report"]
            report = PageReport(
                **{**metadata, "attempts": [Attempt(**a) for a in metadata["attempts"]]}
            )
            report.seconds = 0
            report.attempts.append(
                Attempt("checkpoint", "verified-resume", len(payload["tables"]), 0, 0, 0, 0)
            )
            return (
                [Table.from_dict(t) for t in payload["tables"]],
                report,
                [Issue(**i) for i in payload["issues"]],
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, page: int, tables: list[Table], report: PageReport, issues: list[Issue]) -> None:
        """Only persist a page after all candidate attempts have completed."""
        from dataclasses import asdict

        if report.error:
            return
        payload = {
            "tables": [t.to_dict() for t in tables],
            "report": asdict(report),
            "issues": [asdict(i) for i in issues],
        }
        atomic_json(
            self.folder / f"page-{page:03d}.json",
            {"identity": self.identity, "sha256": digest(payload), "payload": payload},
        )
