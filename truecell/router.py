"""Input validation, bounded page iteration and page-local routing."""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import fitz
from PIL import Image, ImageOps

from .profiling import PageProfile, profile_page

MAX_PAGES = 200
MAX_IMAGE_FRAMES = 50
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class InputError(ValueError):
    """An input cannot safely be processed as a supported document."""


@contextmanager
def open_document(path: str | Path) -> Iterator[fitz.Document]:
    """Open supported files, including multipage TIFF, with a bounded page limit."""
    source = Path(path)
    if not source.is_file():
        raise InputError(f"File not found: {source}")
    document = None
    try:
        if source.suffix.lower() == ".pdf":
            document = fitz.open(source)
        elif source.suffix.lower() in IMAGE_EXTENSIONS:
            document = fitz.open()
            with Image.open(source) as image:
                if getattr(image, "n_frames", 1) > MAX_IMAGE_FRAMES:
                    raise InputError(f"At most {MAX_IMAGE_FRAMES} image frames are supported.")
                for index in range(getattr(image, "n_frames", 1)):
                    image.seek(index)
                    frame = ImageOps.exif_transpose(image.copy()).convert("RGB")
                    import io

                    buffer = io.BytesIO()
                    frame.save(buffer, format="PNG")
                    page = document.new_page(
                        width=frame.width * 72 / 200, height=frame.height * 72 / 200
                    )
                    page.insert_image(page.rect, stream=buffer.getvalue())
        else:
            raise InputError("Use a PDF, PNG, JPEG, TIFF, BMP or WebP file.")
        if document.needs_pass:
            raise InputError("Encrypted PDF requires a password. Export an unlocked copy first.")
        if len(document) > MAX_PAGES:
            raise InputError(f"Document has {len(document)} pages; maximum is {MAX_PAGES}.")
        if not len(document):
            raise InputError("Document contains no pages.")
    except InputError:
        if document is not None:
            document.close()
        raise
    except Exception as exc:
        if document is not None:
            document.close()
        raise InputError(f"Cannot open document: {exc}") from exc
    try:
        yield document
    finally:
        document.close()


def route_page(page: fitz.Page, profile: PageProfile | dict | None = None) -> str:
    """Choose the primary route; the pipeline may add an audited cross-check."""
    evidence = profile or profile_page(page)
    if isinstance(evidence, PageProfile):
        content_mode = evidence.content_mode
        word_count = evidence.native_word_count
        character_count = evidence.native_character_count
    else:
        content_mode = str(evidence.get("content_mode", ""))
        word_count = int(evidence.get("native_word_count", 0))
        character_count = int(evidence.get("native_character_count", 0))
    if content_mode == "empty":
        return "empty"
    # Preserve a potentially useful native candidate when a damaged text layer
    # still contains enough structure. The profile tells the pipeline to OCR it
    # independently rather than silently trusting that candidate.
    if word_count >= 8 and character_count >= 30:
        return "digital"
    return "ocr"


def render_page(page: fitz.Page, dpi: int = 300) -> Image.Image:
    """Render at 300 DPI, capped for unusually large PDF media boxes."""
    width, height = page.rect.width, page.rect.height
    maximum_dpi = min(5500 * 72 / max(width, height), math.sqrt(20_000_000 / (width * height)) * 72)
    actual_dpi = max(1, min(dpi, int(maximum_dpi)))
    pix = page.get_pixmap(dpi=actual_dpi, colorspace=fitz.csRGB, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    image.info["dpi"] = (actual_dpi, actual_dpi)
    return image
