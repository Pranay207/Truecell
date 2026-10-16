"""Input validation, bounded page iteration and page-local routing."""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import fitz
from PIL import Image, ImageOps

MAX_PAGES = 50
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class InputError(ValueError):
    """An input cannot safely be processed as a supported document."""


@contextmanager
def open_document(path: str | Path) -> Iterator[fitz.Document]:
    """Open supported files, including multipage TIFF, with a 50-page limit."""
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
                if getattr(image, "n_frames", 1) > MAX_PAGES:
                    raise InputError("At most 50 image frames are supported.")
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
            raise InputError(f"Document has {len(document)} pages; maximum is 50.")
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


def route_page(page: fitz.Page) -> str:
    """Prefer usable native text; image-heavy text-poor pages need OCR."""
    words = page.get_text("words")
    usable = sum(len(w[4]) for w in words if "\ufffd" not in w[4])
    if len(words) >= 8 and usable >= 30:
        return "digital"
    return "ocr" if page.get_images() or words else "empty"


def render_page(page: fitz.Page, dpi: int = 300) -> Image.Image:
    """Render at 300 DPI, capped for unusually large PDF media boxes."""
    width, height = page.rect.width, page.rect.height
    maximum_dpi = min(5500 * 72 / max(width, height), math.sqrt(20_000_000 / (width * height)) * 72)
    actual_dpi = max(1, min(dpi, int(maximum_dpi)))
    pix = page.get_pixmap(dpi=actual_dpi, colorspace=fitz.csRGB, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    image.info["dpi"] = (actual_dpi, actual_dpi)
    return image
