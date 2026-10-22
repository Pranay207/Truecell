"""Offline OCR, arbitrary small-angle deskew, grid geometry and word-box alignment."""

from __future__ import annotations

import hashlib
import importlib.util
import math
import os
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .anchors import append_summaries, header_tables
from .geometry import rotation_to_original, transformed_box
from .models import Table
from .profiling import normalize_languages
from .table import normalize, words_to_grid


@dataclass(frozen=True)
class OCRAdapter:
    """Explicit boundary for optional local OCR/layout runtimes.

    Adapters receive a preprocessed grayscale page plus normalized language
    codes and return the same word-box records as the bundled engines. They
    are registered by the embedding application, so importing Truecell never
    downloads a model or imports a heavyweight optional runtime.
    """

    recognizer: Callable[[np.ndarray, tuple[str, ...]], list[dict[str, Any]]]
    languages: tuple[str, ...]
    provider: str
    layout_aware: bool
    parallel_safe: bool


_OCR_ADAPTERS: dict[str, OCRAdapter] = {}
_RAPID_MODEL_SHA256 = "c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8"


def register_ocr_adapter(
    name: str,
    recognizer: Callable[[np.ndarray, tuple[str, ...]], list[dict[str, Any]]],
    *,
    languages: Iterable[str] = ("eng",),
    provider: str = "external",
    layout_aware: bool = False,
    parallel_safe: bool = False,
) -> None:
    """Register a locally configured OCR engine without changing dependencies."""
    key = name.strip().lower()
    if not key or key in {"rapidocr", "tesseract", "tesseract-cell"}:
        raise ValueError("Adapter name must be nonempty and must not replace a bundled engine.")
    normalized = normalize_languages(tuple(languages))
    _OCR_ADAPTERS[key] = OCRAdapter(
        recognizer,
        normalized,
        provider.strip() or "external",
        bool(layout_aware),
        bool(parallel_safe),
    )


def unregister_ocr_adapter(name: str) -> None:
    """Remove an optional adapter; primarily useful for application lifecycle/tests."""
    _OCR_ADAPTERS.pop(name.strip().lower(), None)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


@lru_cache(maxsize=1)
def rapid_model_status() -> tuple[bool, str]:
    """Verify the bundled recognizer before advertising it as available."""
    path = Path(__file__).resolve().parents[1] / "models" / "en_PP-OCRv5_rec_mobile.onnx"
    if not path.is_file():
        return False, "bundled English OCR model is missing"
    if hashlib.sha256(path.read_bytes()).hexdigest() != _RAPID_MODEL_SHA256:
        return False, "bundled English OCR model failed its checksum"
    return True, ""


def cell_text(words: list[dict]) -> str:
    """Read words in lines without letting one-pixel box jitter reorder a cell."""
    lines: list[list[dict]] = []
    height = median(w["bottom"] - w["top"] for w in words) if words else 10
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - median(w["top"] for w in lines[-1])) < height * 0.55:
            lines[-1].append(word)
        else:
            lines.append([word])
    return " ".join(w["text"] for line in lines for w in sorted(line, key=lambda w: w["x0"]))


def tesseract_path() -> str | None:
    """Locate the system binary, including common Windows installations."""
    if os.environ.get("TRUECELL_PORTABLE_RAPIDOCR_ONLY") == "1":
        return None
    found = shutil.which("tesseract")
    if found:
        return found
    candidate = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    return str(candidate) if candidate.is_file() else None


def available_engines() -> list[str]:
    """List installed offline engines without downloading or loading a model."""
    engines = []
    if _module_available("pytesseract") and tesseract_path():
        engines.append("tesseract")
    if _module_available("rapidocr_onnxruntime") and rapid_model_status()[0]:
        engines.append("rapidocr")
    engines.extend(sorted(_OCR_ADAPTERS))
    return engines


def configured_languages(value: str | list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Return explicit languages or the local environment preference."""
    if value is None:
        value = os.environ.get("TRUECELL_OCR_LANGUAGES", "eng")
    return normalize_languages(value)


@lru_cache(maxsize=1)
def tesseract_languages() -> tuple[str, ...]:
    """Read installed language packs without downloading any assets."""
    binary = tesseract_path()
    if not binary:
        return ()
    try:
        completed = subprocess.run(
            [binary, "--list-langs"], capture_output=True, text=True, timeout=8, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    values = [line.strip() for line in completed.stdout.splitlines()[1:] if line.strip()]
    return tuple(sorted(set(values)))


def engine_language_coverage(engine: str, languages: tuple[str, ...]) -> tuple[str, ...]:
    """Return requested languages an installed OCR engine can actually read."""
    adapter = _OCR_ADAPTERS.get(engine)
    if adapter:
        supported = set(adapter.languages)
        return tuple(language for language in languages if language in supported)
    if engine.startswith("rapidocr"):
        return tuple(language for language in languages if language == "eng")
    if engine.startswith("tesseract"):
        installed = set(tesseract_languages())
        return tuple(language for language in languages if language in installed)
    # Test and third-party engines retain the pre-language-routing contract.
    return languages


def engine_capabilities(
    languages: str | list[str] | tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    """Describe usable and detected OCR runtimes without importing their models."""
    requested = configured_languages(languages)
    tesseract_installed = _module_available("pytesseract") and bool(tesseract_path())
    rapid_installed = _module_available("rapidocr_onnxruntime")
    rapid_model_ready, rapid_model_reason = rapid_model_status() if rapid_installed else (False, "")
    rapid_available = rapid_installed and rapid_model_ready
    capabilities: dict[str, dict[str, Any]] = {
        "tesseract": {
            "available": tesseract_installed,
            "installed": tesseract_installed,
            "provider": "builtin-system",
            "layout_aware": False,
            "parallel_safe": True,
            "requested_language_coverage": list(
                engine_language_coverage("tesseract", requested) if tesseract_installed else ()
            ),
            "reason": (
                "" if tesseract_installed else "pytesseract or the Tesseract binary is unavailable"
            ),
        },
        "rapidocr": {
            "available": rapid_available,
            "installed": rapid_installed,
            "provider": "bundled-onnx",
            "layout_aware": False,
            "parallel_safe": True,
            "requested_language_coverage": list(
                engine_language_coverage("rapidocr", requested) if rapid_available else ()
            ),
            "reason": (
                ""
                if rapid_available
                else rapid_model_reason
                if rapid_installed
                else "rapidocr-onnxruntime is unavailable"
            ),
        },
    }
    for name, adapter in sorted(_OCR_ADAPTERS.items()):
        capabilities[name] = {
            "available": True,
            "installed": True,
            "provider": adapter.provider,
            "layout_aware": adapter.layout_aware,
            "parallel_safe": adapter.parallel_safe,
            "requested_language_coverage": list(engine_language_coverage(name, requested)),
            "reason": "",
        }
    if "paddleocr" not in capabilities:
        paddle_installed = _module_available("paddleocr") and _module_available("paddle")
        capabilities["paddleocr"] = {
            "available": False,
            "installed": paddle_installed,
            "provider": "optional-adapter",
            "layout_aware": True,
            "parallel_safe": False,
            "requested_language_coverage": [],
            "reason": (
                "installed but no local Truecell adapter is registered; automatic model downloads are disabled"
                if paddle_installed
                else "PaddleOCR and its Paddle runtime are not installed"
            ),
        }
    return capabilities


def engines_can_run_concurrently(engines: Iterable[str]) -> bool:
    """Return whether distinct engines opted into one bounded parallel batch."""
    names = list(engines)
    if len(names) != len(set(names)):
        return False
    capabilities = engine_capabilities()
    return all(capabilities.get(name, {}).get("parallel_safe", False) for name in names)


def order_engines(engines: list[str], languages: tuple[str, ...]) -> list[str]:
    """Prefer the engine with the greatest requested-language coverage."""
    positions = {engine: index for index, engine in enumerate(engines)}
    return sorted(
        engines,
        key=lambda engine: (-len(engine_language_coverage(engine, languages)), positions[engine]),
    )


@lru_cache(maxsize=1)
def rapid_engine():
    """Lazily load bundled ONNX models with bounded CPU threading."""
    return english_engine()


@lru_cache(maxsize=1)
def english_engine():
    """Load a checksum-verified upstream English recognizer, never download it."""
    from rapidocr_onnxruntime import RapidOCR

    path = Path(__file__).resolve().parents[1] / "models" / "en_PP-OCRv5_rec_mobile.onnx"
    if not rapid_model_status()[0]:
        raise ValueError("Bundled English OCR model is missing or failed its checksum.")
    return RapidOCR(rec_model_path=str(path), intra_op_num_threads=2, inter_op_num_threads=1)


def tight_ink(gray: np.ndarray) -> np.ndarray | None:
    """Trim a padded single cell to text components, excluding border remnants."""
    if gray.size < 16 or float(gray.std()) < 4:
        return None
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    components = []
    for x, y, w, h, area in stats[1:]:
        if (
            area >= 4
            and h < gray.shape[0] * 0.9
            and w < gray.shape[1] * 0.9
            and x > 0
            and y > 0
            and x + w < gray.shape[1]
            and y + h < gray.shape[0]
        ):
            components.append((x, y, x + w, y + h))
    if not components:
        return None
    x0, y0 = min(c[0] for c in components), min(c[1] for c in components)
    x1, y1 = max(c[2] for c in components), max(c[3] for c in components)
    return cv2.copyMakeBorder(gray[y0:y1, x0:x1], 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)


def reread_headers(
    gray: np.ndarray, xs: list[int], ys: list[int]
) -> list[tuple[str, float] | None]:
    """Read cropped headers at two scales; return only strong exact agreements."""
    crops = []
    indices = []
    for c in range(len(xs) - 1):
        crop = gray[ys[0] + 8 : ys[1] - 8, xs[c] + 9 : xs[c + 1] - 9].copy()
        if crop.size and np.median(crop) < 150:
            crop = 255 - crop
        tight = tight_ink(crop)
        if tight is not None:
            crop = cv2.cvtColor(tight, cv2.COLOR_GRAY2BGR)
            crops.extend(
                [
                    crop,
                    cv2.resize(crop, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC),
                ]
            )
            indices.append(c)
    output = [None] * (len(xs) - 1)
    if crops:
        readings, _ = english_engine().text_rec(crops)
        for i, c in enumerate(indices):
            a, b = readings[2 * i], readings[2 * i + 1]
            if a[0] == b[0] and a[0].strip() and min(float(a[1]), float(b[1])) >= 0.95:
                output[c] = (a[0].strip(), min(float(a[1]), float(b[1])))
    return output


def preprocess(image: Image.Image, alternate: bool = False) -> tuple[np.ndarray, float]:
    """Denoise, improve contrast and deskew using a robust median Hough angle."""
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    if max(gray.shape) > 5500:
        scale = 5500 / max(gray.shape)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    small_scale = min(1, 1600 / max(gray.shape))
    small = cv2.resize(gray, None, fx=small_scale, fy=small_scale)
    edges = cv2.Canny(small, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 1800,
        threshold=60,
        minLineLength=max(40, small.shape[1] // 12),
        maxLineGap=20,
    )
    angles = []
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if abs(angle) <= 15:
                angles.append(angle)
    angle = median(angles) if len(angles) >= 3 else 0.0
    if abs(angle) > 0.15:
        h, w = gray.shape
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
        gray = cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)
    gray = cv2.medianBlur(gray, 3)
    if alternate:
        gray = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 13
        )
    else:
        gray = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(gray)
    return gray, angle


def rectify_perspective(image: Image.Image) -> tuple[Image.Image, tuple | None]:
    """Rectify a dominant quadrilateral table only when opposing edges diverge."""
    gray = np.asarray(image.convert("L"))
    scale = min(1, 1600 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale)
    binary = cv2.adaptiveThreshold(
        small, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 35, 12
    )
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    large = [c for c in contours if cv2.contourArea(c) > small.size * 0.02]
    if not large:
        return image, None
    hull = cv2.convexHull(np.concatenate(large))
    quad = cv2.approxPolyDP(hull, 0.025 * cv2.arcLength(hull, True), True)
    if len(quad) != 4 or cv2.contourArea(quad) < small.size * 0.12:
        return image, None
    points = quad.reshape(4, 2).astype(np.float32) / scale
    ordered = np.zeros((4, 2), np.float32)
    sums, differences = points.sum(axis=1), np.diff(points, axis=1).ravel()
    ordered[0], ordered[2] = points[np.argmin(sums)], points[np.argmax(sums)]
    ordered[1], ordered[3] = (
        points[np.argmin(differences)],
        points[np.argmax(differences)],
    )
    top, right, bottom, left = [
        float(np.linalg.norm(ordered[(i + 1) % 4] - ordered[i])) for i in range(4)
    ]
    if (
        min(top, right, bottom, left) < 30
        or max(abs(top - bottom) / max(top, bottom), abs(left - right) / max(left, right)) < 0.02
    ):
        return image, None
    width, height = round(max(top, bottom)), round(max(left, right))
    destination = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    matrix = cv2.getPerspectiveTransform(ordered, destination)
    transformed = cv2.warpPerspective(
        np.asarray(image.convert("RGB")),
        matrix,
        (width, height),
        borderValue=(255, 255, 255),
    )
    transformed = cv2.copyMakeBorder(
        transformed, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )
    result = Image.fromarray(transformed)
    result.info.update(image.info)
    padding_inverse = np.array([[1, 0, -20], [0, 1, -20], [0, 0, 1]], float)
    result.info["source_transform"] = (np.linalg.inv(matrix) @ padding_inverse).tolist()
    return result, (
        float(points[:, 0].min()),
        float(points[:, 1].min()),
        float(points[:, 0].max()),
        float(points[:, 1].max()),
    )


def _runs(indices: np.ndarray, gap: int = 3) -> list[int]:
    groups: list[list[int]] = []
    for index in indices.tolist():
        if groups and index - groups[-1][-1] <= gap:
            groups[-1].append(index)
        else:
            groups.append([index])
    return [round(float(np.mean(g))) for g in groups]


def grid_regions(
    gray: np.ndarray,
) -> tuple[list[tuple[list[int], list[int]]], np.ndarray]:
    """Find individual ruled table regions and create a line-removal mask."""
    # Global Otsu can discard pale gray ruling when a dark header dominates.
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 35, 12
    )
    h, w = gray.shape
    horizontal = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(35, w // 35), 1)),
    )
    vertical = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, h // 35))),
    )
    mask = cv2.bitwise_or(horizontal, vertical)
    connected = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for contour in contours:
        x, y, rw, rh = cv2.boundingRect(contour)
        if rw < w * 0.15 or rh < 40:
            continue
        crop_v = vertical[y : y + rh, x : x + rw]
        crop_h = horizontal[y : y + rh, x : x + rw]
        xs = [x + c for c in _runs(np.where(np.count_nonzero(crop_v, axis=0) > rh * 0.35)[0])]
        ys = [y + r for r in _runs(np.where(np.count_nonzero(crop_h, axis=1) > rw * 0.35)[0])]
        if len(xs) >= 3:
            # Adaptive thresholding can turn white letters inside a filled
            # header into several false horizontal separators. The original
            # gray image identifies the continuous dark band independently.
            dark = np.where(np.median(gray[y : y + rh, xs[0] : xs[-1]], axis=1) < 120)[0]
            bands = []
            # White glyph rows can interrupt the dark median. Bridge those
            # interruptions using the ordinary body-row spacing as a scale.
            bridge = max(2, round(float(np.median(np.diff(ys))) * 0.65)) if len(ys) > 1 else 2
            for row in dark.tolist():
                if bands and row - bands[-1][-1] <= bridge:
                    bands[-1].append(row)
                else:
                    bands.append([row])
            for band in bands:
                if 8 <= len(band) <= rh * 0.4:
                    top, bottom = y + band[0], y + band[-1] + 1
                    ys = [row for row in ys if row < top - 4 or row > bottom + 4]
                    ys.extend([top, bottom])
            ys = _runs(np.array(sorted(ys), dtype=int))
        if len(xs) >= 3 and len(ys) >= 3:
            regions.append((xs, ys))
    return sorted(regions, key=lambda r: (r[1][0], r[0][0])), mask


def grid_topology(
    xs: list[int], ys: list[int], line_mask: np.ndarray, gray: np.ndarray | None = None
) -> tuple[list[list[tuple[int, int]]], list[list[tuple[int, int, int, int] | None]]]:
    """Recover merged grid components from locally missing separator segments.

    Global x/y lines establish a table, while a missing segment between two
    adjacent slots is positive evidence that those slots share one source cell.
    The returned owner map always points at the component's top-left slot.
    """
    rows, columns = len(ys) - 1, len(xs) - 1
    parents = list(range(rows * columns))

    def find(item: int) -> int:
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parents[max(a, b)] = min(a, b)

    def slot_has_content(row: int, column: int) -> bool:
        """Detect independent ink before interpreting a broken rule as a merge."""
        if gray is None:
            return False
        pad_x = max(3, round((xs[column + 1] - xs[column]) * 0.04))
        pad_y = max(3, round((ys[row + 1] - ys[row]) * 0.08))
        crop = gray[
            ys[row] + pad_y : ys[row + 1] - pad_y,
            xs[column] + pad_x : xs[column + 1] - pad_x,
        ]
        if crop.size == 0:
            return False
        if np.median(crop) < 150:
            return True
        return tight_ink(crop) is not None

    def horizontal_present(boundary: int, column: int) -> bool:
        y = ys[boundary]
        pad = max(3, round((xs[column + 1] - xs[column]) * 0.06))
        crop = line_mask[
            max(0, y - 3) : min(line_mask.shape[0], y + 4),
            xs[column] + pad : xs[column + 1] - pad,
        ]
        if crop.size == 0:
            return True
        coverage = np.count_nonzero(np.any(crop > 0, axis=0)) / max(1, crop.shape[1])
        return coverage >= 0.25

    def vertical_present(row: int, boundary: int) -> bool:
        # A filled header band can hide pale separators from the binary line
        # mask even though it contains independent labels in every column.
        # Treat a dark band as column-preserving evidence; otherwise the whole
        # header is incorrectly collapsed into one horizontally merged cell.
        if gray is not None:
            band = gray[
                ys[row] + 4 : ys[row + 1] - 3,
                xs[0] + 4 : xs[-1] - 3,
            ]
            if band.size and np.median(band) < 150:
                return True
        x = xs[boundary]
        pad = max(3, round((ys[row + 1] - ys[row]) * 0.06))
        crop = line_mask[
            ys[row] + pad : ys[row + 1] - pad,
            max(0, x - 3) : min(line_mask.shape[1], x + 4),
        ]
        if crop.size == 0:
            return True
        coverage = np.count_nonzero(np.any(crop > 0, axis=1)) / max(1, crop.shape[0])
        return coverage >= 0.25

    for boundary in range(1, rows):
        for column in range(columns):
            if not horizontal_present(boundary, column):
                above, below = boundary - 1, boundary
                if not (slot_has_content(above, column) and slot_has_content(below, column)):
                    union(above * columns + column, below * columns + column)
    for row in range(rows):
        for boundary in range(1, columns):
            if not vertical_present(row, boundary):
                left, right = boundary - 1, boundary
                if not (slot_has_content(row, left) and slot_has_content(row, right)):
                    union(row * columns + left, row * columns + right)

    members: dict[int, list[tuple[int, int]]] = {}
    for row in range(rows):
        for column in range(columns):
            members.setdefault(find(row * columns + column), []).append((row, column))
    owners = [[(row, column) for column in range(columns)] for row in range(rows)]
    boxes: list[list[tuple[int, int, int, int] | None]] = [
        [None for _ in range(columns)] for _ in range(rows)
    ]
    for cells in members.values():
        top = min(row for row, _ in cells)
        left = min(column for _, column in cells)
        bottom = max(row for row, _ in cells)
        right = max(column for _, column in cells)
        if len(cells) != (bottom - top + 1) * (right - left + 1):
            for row, column in cells:
                owners[row][column] = (row, column)
                boxes[row][column] = (xs[column], ys[row], xs[column + 1], ys[row + 1])
            continue
        owner = (top, left)
        for row, column in cells:
            owners[row][column] = owner
        boxes[top][left] = (xs[left], ys[top], xs[right + 1], ys[bottom + 1])
    return owners, boxes


def recognize(
    gray: np.ndarray,
    engine: str,
    *,
    languages: str | list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """Return text boxes with engine confidence; no lexical substitutions."""
    adapter = _OCR_ADAPTERS.get(engine)
    if adapter:
        requested = configured_languages(languages)
        supported = engine_language_coverage(engine, requested)
        raw_words = adapter.recognizer(gray, supported)
        words = []
        for item in raw_words:
            required = {"x0", "x1", "top", "bottom", "text", "confidence"}
            if not isinstance(item, dict) or not required.issubset(item):
                raise ValueError(f"OCR adapter {engine!r} returned an invalid word record.")
            text = str(item["text"]).strip()
            if not text:
                continue
            x0, x1 = float(item["x0"]), float(item["x1"])
            top, bottom = float(item["top"]), float(item["bottom"])
            confidence = float(item["confidence"])
            coordinates = (x0, x1, top, bottom)
            if (
                not all(math.isfinite(value) for value in coordinates)
                or x1 <= x0
                or bottom <= top
                or not math.isfinite(confidence)
            ):
                raise ValueError(f"OCR adapter {engine!r} returned invalid geometry/confidence.")
            words.append(
                {
                    "x0": x0,
                    "x1": x1,
                    "top": top,
                    "bottom": bottom,
                    "text": text,
                    "confidence": max(0.0, min(1.0, confidence)),
                }
            )
        return words
    if engine == "rapidocr":
        result, _ = rapid_engine()(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
        words = []
        for box, text, confidence in result or []:
            points = np.array(box)
            words.append(
                {
                    "x0": float(points[:, 0].min()),
                    "x1": float(points[:, 0].max()),
                    "top": float(points[:, 1].min()),
                    "bottom": float(points[:, 1].max()),
                    "text": text,
                    "confidence": float(confidence),
                }
            )
        return words
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = tesseract_path() or "tesseract"
    mode = 7 if engine == "tesseract-cell" else 6
    requested = configured_languages(languages)
    supported = engine_language_coverage(engine, requested)
    options = {
        "config": f"--psm {mode}",
        "output_type": pytesseract.Output.DICT,
        "timeout": 90,
    }
    if supported:
        options["lang"] = "+".join(supported)
    data = pytesseract.image_to_data(gray, **options)
    return [
        {
            "x0": data["left"][i],
            "x1": data["left"][i] + data["width"][i],
            "top": data["top"][i],
            "bottom": data["top"][i] + data["height"][i],
            "text": text,
            "confidence": max(0, float(data["conf"][i])) / 100,
        }
        for i, text in enumerate(data["text"])
        if text.strip()
    ]


def recognize_grid(
    gray: np.ndarray,
    regions: list[tuple[list[int], list[int]]],
    component_boxes: list[list[list[tuple[int, int, int, int] | None]]] | None = None,
) -> list[dict]:
    """Recognize known grid cells directly, avoiding word-detection digit loss."""
    crops = []
    positions = []
    for region_index, (xs, ys) in enumerate(regions):
        boxes = component_boxes[region_index] if component_boxes is not None else None
        for r in range(len(ys) - 1):
            for c in range(len(xs) - 1):
                source_box = (
                    boxes[r][c] if boxes is not None else (xs[c], ys[r], xs[c + 1], ys[r + 1])
                )
                if source_box is None:
                    continue
                x0, y0, x1, y1 = source_box
                crop = gray[y0 + 6 : y1 - 5, x0 + 6 : x1 - 5]
                tight = tight_ink(crop)
                if tight is None:
                    continue
                binary = cv2.threshold(tight, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
                active = np.where(np.count_nonzero(binary, axis=1) > 0)[0]
                bands = []
                for y in active.tolist():
                    if bands and y - bands[-1][-1] <= 4:
                        bands[-1].append(y)
                    else:
                        bands.append([y])
                for line_index, band in enumerate(bands):
                    if len(band) < 3:
                        continue
                    line = tight[max(0, band[0] - 2) : min(tight.shape[0], band[-1] + 3)]
                    crops.append(cv2.cvtColor(line, cv2.COLOR_GRAY2BGR))
                    positions.append(
                        (
                            x0 + 6,
                            x1 - 6,
                            y0 + 8 + line_index * 12,
                            y0 + 18 + line_index * 12,
                        )
                    )
    if not crops:
        return []
    readings, _ = english_engine().text_rec(crops)
    return [
        {
            "x0": p[0],
            "x1": p[1],
            "top": p[2],
            "bottom": p[3],
            "text": reading[0],
            "confidence": float(reading[1]),
        }
        for p, reading in zip(positions, readings)
        if reading[0].strip()
    ]


def extract_image(
    image: Image.Image,
    page: int,
    engine: str = "rapidocr",
    *,
    alternate: bool = False,
    rotation: int = 0,
    perspective: bool = False,
    languages: str | list[str] | tuple[str, ...] | None = None,
) -> list[Table]:
    """Reconstruct ruled grids first; fall back to recurring word-box alignment."""
    original_width, original_height = image.size
    original_dpi = image.info.get("dpi", (300, 300))
    to_original = rotation_to_original(rotation, original_width, original_height)
    if rotation:
        image = image.rotate(rotation, expand=True, fillcolor="white")
    source_quad = None
    if perspective:
        image, source_quad = rectify_perspective(image)
    gray, angle = preprocess(image, False)
    if source_quad:
        to_original = to_original @ np.array(image.info["source_transform"])
    scale_x, scale_y = image.width / gray.shape[1], image.height / gray.shape[0]
    scale_matrix = np.diag([scale_x, scale_y, 1])
    deskew = cv2.getRotationMatrix2D(
        (gray.shape[1] / 2, gray.shape[0] / 2), angle if abs(angle) > 0.15 else 0, 1
    )
    pixel_to_original = to_original @ scale_matrix @ np.linalg.inv(np.vstack([deskew, [0, 0, 1]]))
    point_map = np.diag([72 / original_dpi[0], 72 / original_dpi[1], 1]) @ pixel_to_original
    regions, mask = grid_regions(gray)
    topologies = [grid_topology(xs, ys, mask, gray) for xs, ys in regions]
    component_boxes = [boxes for _owners, boxes in topologies]
    cleaned = gray.copy()
    if not regions:
        # A single underline can join every header into a glyph-like blob.
        # Remove only long, thin rule components, preserving filled headings.
        _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        thin_rules = np.zeros_like(mask)
        for label, (x, y, width, height, area) in enumerate(stats[1:], 1):
            if width > gray.shape[1] * 0.25 and width > height * 25:
                thin_rules[labels == label] = 255
        cleaned[cv2.dilate(thin_rules, np.ones((3, 3), np.uint8)) > 0] = 255
    # Whiten inferred rule coordinates, not the entire morphology mask: the
    # latter can erase filled header backgrounds and the text they surround.
    for region_index, (xs, ys) in enumerate(regions):
        owners, _boxes = topologies[region_index]
        # OCR engines struggle with white text on dark, filled header bands.
        for y0, y1 in zip(ys, ys[1:]):
            band = cleaned[y0 + 4 : y1 - 3, xs[0] + 4 : xs[-1] - 3]
            if band.size and np.median(band) < 150:
                cleaned[y0 + 4 : y1 - 3, xs[0] + 4 : xs[-1] - 3] = 255 - band
        for boundary, x in enumerate(xs):
            if boundary in {0, len(xs) - 1}:
                cv2.line(cleaned, (x, ys[0]), (x, ys[-1]), 255, 7)
                continue
            for row in range(len(ys) - 1):
                if owners[row][boundary - 1] != owners[row][boundary]:
                    cv2.line(cleaned, (x, ys[row]), (x, ys[row + 1]), 255, 7)
        for boundary, y in enumerate(ys):
            if boundary in {0, len(ys) - 1}:
                cv2.line(cleaned, (xs[0], y), (xs[-1], y), 255, 7)
                continue
            for column in range(len(xs) - 1):
                if owners[boundary - 1][column] != owners[boundary][column]:
                    cv2.line(cleaned, (xs[column], y), (xs[column + 1], y), 255, 7)
    if alternate and engine != "tesseract":
        # Normalize dark backgrounds before binarization to preserve header text.
        cleaned = cv2.adaptiveThreshold(
            cleaned, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 13
        )
    if source_quad:
        # A white rule painted across a shaded photograph becomes a false edge.
        # Remove the slowly varying illumination before OCR layout analysis.
        cleaned = cv2.divide(cleaned, cv2.GaussianBlur(cleaned, (0, 0), 25), scale=255)
    requested_languages = configured_languages(languages)
    words = (
        recognize_grid(cleaned, regions, component_boxes)
        if engine == "rapidocr" and regions and requested_languages == ("eng",)
        else (
            recognize(cleaned, engine)
            if requested_languages == ("eng",)
            else recognize(cleaned, engine, languages=requested_languages)
        )
    )
    confidence = median(w["confidence"] for w in words) if words else 0
    h, w = gray.shape
    dpi_x, dpi_y = image.info.get("dpi", (300, 300))
    sx, sy = image.width * 72 / dpi_x / w, image.height * 72 / dpi_y / h
    tables = []
    for region_index, (xs, ys) in enumerate(regions):
        owners, pixel_boxes = topologies[region_index]
        grid = [[[] for _ in range(len(xs) - 1)] for _ in range(len(ys) - 1)]
        for word in words:
            cx, cy = (word["x0"] + word["x1"]) / 2, (word["top"] + word["bottom"]) / 2
            c = next((i for i in range(len(xs) - 1) if xs[i] <= cx < xs[i + 1]), None)
            r = next((i for i in range(len(ys) - 1) if ys[i] <= cy < ys[i + 1]), None)
            if r is not None and c is not None:
                owner_row, owner_column = owners[r][c]
                grid[owner_row][owner_column].append(word)
        rechecks = []
        original_readings = [[cell_text(cell) for cell in row] for row in grid]
        if alternate and engine == "tesseract":
            for r, row in enumerate(grid):
                for c, cell in enumerate(row):
                    if cell and min(word["confidence"] for word in cell) < 0.80:
                        source_box = pixel_boxes[r][c]
                        if source_box is None:
                            continue
                        x0, y0, x1, y1 = source_box
                        crop = cleaned[y0 + 5 : y1 - 4, x0 + 5 : x1 - 4]
                        if not crop.size:
                            continue
                        recheck_image = cv2.copyMakeBorder(
                            crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255
                        )
                        rechecked = (
                            recognize(recheck_image, "tesseract-cell")
                            if requested_languages == ("eng",)
                            else recognize(
                                recheck_image,
                                "tesseract-cell",
                                languages=requested_languages,
                            )
                        )
                        if rechecked and min(w["confidence"] for w in rechecked) > min(
                            w["confidence"] for w in cell
                        ):
                            old, new = cell_text(cell), cell_text(rechecked)
                            if old != new:
                                rechecks.append(
                                    f"Cell recheck at grid row {r + 1}, column {c + 1}: {old!r} -> {new!r}; compare source."
                                )
                            grid[r][c] = rechecked
        raw = [[cell_text(cell) for cell in row] for row in grid]
        boxes = [
            [tuple(transformed_box(box, point_map)) if box is not None else None for box in row]
            for row in pixel_boxes
        ]
        row_indices: list[int] = []
        table = normalize(
            raw,
            page,
            tuple(transformed_box((xs[0], ys[0], xs[-1], ys[-1]), point_map)),
            f"ocr-{engine}",
            confidence,
            boxes,
            row_indices=row_indices,
            ruled_geometry=True,
        )
        if table:
            single_header = table.header_detected and all(len(s) == 1 for s in table.header_sources)
            header_index = (
                next(
                    (
                        r
                        for r in range(row_indices[0])
                        if all(
                            sources[0].get("bbox") == list(boxes[r][c])
                            for c, sources in enumerate(table.header_sources)
                        )
                    ),
                    None,
                )
                if row_indices and single_header
                else None
            )
            for c, sources in enumerate(table.header_sources):
                for record in sources:
                    source_row = int(record.get("source_row", (header_index or 0) + 1)) - 1
                    source_column = int(record.get("source_column", c + 1)) - 1
                    source_cell = (
                        grid[source_row][source_column]
                        if 0 <= source_row < len(grid)
                        and 0 <= source_column < len(grid[source_row])
                        else []
                    )
                    record["confidence"] = min(
                        (word["confidence"] for word in source_cell), default=0
                    )
            if (
                alternate
                and engine == "tesseract"
                and header_index is not None
                and requested_languages == ("eng",)
            ):
                try:
                    verified_headers = reread_headers(gray, xs, ys[header_index : header_index + 2])
                    for c, reading in enumerate(verified_headers):
                        if reading and reading[0] != table.headers[c]:
                            old = table.headers[c]
                            table.headers[c] = reading[0]
                            table.header_sources[c].append(
                                {
                                    "page": page,
                                    "bbox": list(boxes[header_index][c]),
                                    "text": reading[0],
                                    "engine": "rapidocr-English-v5",
                                    "confidence": reading[1],
                                    "role": "header_recheck",
                                    "initial_reading": old,
                                    "coordinates": "page points",
                                }
                            )
                except (ValueError, ImportError, RuntimeError) as exc:
                    table.notes.append(
                        f"English header verification unavailable: {type(exc).__name__}."
                    )
            for r, raw_index in enumerate(row_indices):
                row = grid[raw_index]
                for c, cell in enumerate(row):
                    score = min((word["confidence"] for word in cell), default=0)
                    for record in table.cell_sources[r][c]:
                        source_row = int(record.get("source_row", raw_index + 1)) - 1
                        source_column = int(record.get("source_column", c + 1)) - 1
                        source_cell = (
                            grid[source_row][source_column]
                            if 0 <= source_row < len(grid)
                            and 0 <= source_column < len(grid[source_row])
                            else []
                        )
                        score = min((word["confidence"] for word in source_cell), default=score)
                        record["confidence"] = score
                        record["initial_reading"] = (
                            original_readings[source_row][source_column]
                            if 0 <= source_row < len(original_readings)
                            and 0 <= source_column < len(original_readings[source_row])
                            else ""
                        )
                    table.cell_confidence[(r, c)] = score
            table.notes.append(
                f"OCR {engine}; deskew correction {angle:.2f} degrees; values require source review."
            )
            table.notes.extend(rechecks)
            summary_words = words
            if engine == "rapidocr":
                # Grid-only recognition cannot see totals below the rules.
                # Read a bounded footer strip only when it contains ink.
                x0, y0 = max(0, xs[0] - 10), ys[-1] + 3
                x1, y1 = min(w, xs[-1] + 10), min(h, y0 + (ys[1] - ys[0]) * 7)
                summary_words = []
                if y1 - y0 >= 32 and x1 > x0:
                    footer = cleaned[y0:y1, x0:x1]
                    if np.count_nonzero(footer < 160) > 20:
                        # Preserve a nonzero height when RapidOCR rounds a
                        # very wide crop to multiples of 32 pixels.
                        footer = cv2.copyMakeBorder(
                            footer, 64, 64, 0, 0, cv2.BORDER_CONSTANT, value=255
                        )
                        try:
                            readings = (
                                recognize(footer, engine)
                                if requested_languages == ("eng",)
                                else recognize(footer, engine, languages=requested_languages)
                            )
                        except Exception as exc:
                            readings = []
                            table.notes.append(
                                f"Summary OCR unavailable ({type(exc).__name__}); inspect below the table."
                            )
                        summary_words = [
                            {
                                **word,
                                "x0": word["x0"] + x0,
                                "x1": word["x1"] + x0,
                                "top": word["top"] + y0 - 64,
                                "bottom": word["bottom"] + y0 - 64,
                            }
                            for word in readings
                        ]
            append_grid_summaries(table, summary_words, xs, ys, point_map)
            tables.append(table)
    if not tables:
        scaled = [
            {
                **word,
                "x0": word["x0"] * sx,
                "x1": word["x1"] * sx,
                "top": word["top"] * sy,
                "bottom": word["bottom"] * sy,
            }
            for word in words
        ]
        tables = header_tables(scaled, page, engine=f"ocr-{engine}-anchors", font_evidence=False)
        if not tables:
            tables = words_to_grid(scaled, page, f"ocr-{engine}-words", w * sx, h * sy)
        for table in tables:
            table.confidence = min(confidence, table.confidence)
            # Word reconstruction used the processed image's point coordinates.
            # Bring those boxes back through the same deskew/perspective map.
            processed_points_to_original = point_map @ np.diag([1 / sx, 1 / sy, 1])
            table.bbox = tuple(transformed_box(table.bbox, processed_points_to_original))
            for record in table.page_summaries:
                if record.get("bbox"):
                    record["bbox"] = transformed_box(record["bbox"], processed_points_to_original)
            for row in [table.header_sources] + table.cell_sources:
                for cell in row:
                    for record in cell:
                        if record.get("bbox"):
                            record["bbox"] = transformed_box(
                                record["bbox"], processed_points_to_original
                            )
    if source_quad:
        for table in tables:
            table.notes.append(
                "Perspective rectification inferred from a dominant table outline; verify row and column alignment."
            )
    return tables


def append_grid_summaries(
    table: Table, words: list[dict], xs: list[int], ys: list[int], point_map: np.ndarray
) -> None:
    """Group unruled summaries upright, then map their evidence to the source."""
    upright = Table(
        table.headers[:], table.rows[:], table.page, (xs[0], ys[0], xs[-1], ys[-1]), table.engine
    )
    upright.cell_sources = [
        [[{"bbox": [xs[c], ys[0], xs[c + 1], ys[-1]]}] for c in range(len(xs) - 1)]
        for _ in table.rows
    ]
    append_summaries(upright, words)
    for r in range(len(table.rows), len(upright.rows)):
        table.rows.append(upright.rows[r])
        sources = upright.cell_sources[r]
        for c, cell in enumerate(sources):
            for record in cell:
                record["bbox"] = transformed_box(record["bbox"], point_map)
                table.cell_confidence[r, c] = record["confidence"]
        table.cell_sources.append(sources)
        table.provenance.append([(table.page, len(table.provenance) + 1)])
        table.row_engines.append(table.engine)
    table.notes.extend(note for note in upright.notes if note not in table.notes)
