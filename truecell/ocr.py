"""Offline OCR, arbitrary small-angle deskew, grid geometry and word-box alignment."""

from __future__ import annotations

import hashlib
import importlib.util
import math
import os
import shutil
from functools import lru_cache
from pathlib import Path
from statistics import median

import cv2
import numpy as np
from PIL import Image

from .anchors import append_summaries, header_tables
from .geometry import rotation_to_original, transformed_box
from .models import Table
from .table import normalize, words_to_grid


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
    if importlib.util.find_spec("pytesseract") and tesseract_path():
        engines.append("tesseract")
    if importlib.util.find_spec("rapidocr_onnxruntime"):
        engines.append("rapidocr")
    return engines


@lru_cache(maxsize=1)
def rapid_engine():
    """Lazily load bundled ONNX models with bounded CPU threading."""
    return english_engine()


@lru_cache(maxsize=1)
def english_engine():
    """Load a checksum-verified upstream English recognizer, never download it."""
    from rapidocr_onnxruntime import RapidOCR

    path = Path(__file__).resolve().parents[1] / "models" / "en_PP-OCRv5_rec_mobile.onnx"
    expected = "c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
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


def recognize(gray: np.ndarray, engine: str) -> list[dict]:
    """Return text boxes with engine confidence; no lexical substitutions."""
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
    data = pytesseract.image_to_data(
        gray, config=f"--psm {mode}", output_type=pytesseract.Output.DICT, timeout=90
    )
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


def recognize_grid(gray: np.ndarray, regions: list[tuple[list[int], list[int]]]) -> list[dict]:
    """Recognize known grid cells directly, avoiding word-detection digit loss."""
    crops = []
    positions = []
    for xs, ys in regions:
        for r in range(len(ys) - 1):
            for c in range(len(xs) - 1):
                crop = gray[ys[r] + 6 : ys[r + 1] - 5, xs[c] + 6 : xs[c + 1] - 5]
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
                            xs[c] + 6,
                            xs[c + 1] - 6,
                            ys[r] + 8 + line_index * 12,
                            ys[r] + 18 + line_index * 12,
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
    for xs, ys in regions:
        # OCR engines struggle with white text on dark, filled header bands.
        for y0, y1 in zip(ys, ys[1:]):
            band = cleaned[y0 + 4 : y1 - 3, xs[0] + 4 : xs[-1] - 3]
            if band.size and np.median(band) < 150:
                cleaned[y0 + 4 : y1 - 3, xs[0] + 4 : xs[-1] - 3] = 255 - band
        for x in xs:
            cv2.line(cleaned, (x, ys[0]), (x, ys[-1]), 255, 7)
        for y in ys:
            cv2.line(cleaned, (xs[0], y), (xs[-1], y), 255, 7)
    if alternate and engine != "tesseract":
        # Normalize dark backgrounds before binarization to preserve header text.
        cleaned = cv2.adaptiveThreshold(
            cleaned, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 13
        )
    if source_quad:
        # A white rule painted across a shaded photograph becomes a false edge.
        # Remove the slowly varying illumination before OCR layout analysis.
        cleaned = cv2.divide(cleaned, cv2.GaussianBlur(cleaned, (0, 0), 25), scale=255)
    words = (
        recognize_grid(cleaned, regions)
        if engine == "rapidocr" and regions
        else recognize(cleaned, engine)
    )
    confidence = median(w["confidence"] for w in words) if words else 0
    h, w = gray.shape
    dpi_x, dpi_y = image.info.get("dpi", (300, 300))
    sx, sy = image.width * 72 / dpi_x / w, image.height * 72 / dpi_y / h
    tables = []
    for xs, ys in regions:
        grid = [[[] for _ in range(len(xs) - 1)] for _ in range(len(ys) - 1)]
        for word in words:
            cx, cy = (word["x0"] + word["x1"]) / 2, (word["top"] + word["bottom"]) / 2
            c = next((i for i in range(len(xs) - 1) if xs[i] <= cx < xs[i + 1]), None)
            r = next((i for i in range(len(ys) - 1) if ys[i] <= cy < ys[i + 1]), None)
            if r is not None and c is not None:
                grid[r][c].append(word)
        rechecks = []
        original_readings = [[cell_text(cell) for cell in row] for row in grid]
        if alternate and engine == "tesseract":
            for r, row in enumerate(grid):
                for c, cell in enumerate(row):
                    if cell and min(word["confidence"] for word in cell) < 0.80:
                        crop = cleaned[ys[r] + 5 : ys[r + 1] - 4, xs[c] + 5 : xs[c + 1] - 4]
                        if not crop.size:
                            continue
                        rechecked = recognize(
                            cv2.copyMakeBorder(
                                crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255
                            ),
                            "tesseract-cell",
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
            [
                tuple(transformed_box((xs[c], ys[r], xs[c + 1], ys[r + 1]), point_map))
                for c in range(len(xs) - 1)
            ]
            for r in range(len(ys) - 1)
        ]
        row_indices: list[int] = []
        table = normalize(
            raw,
            page,
            tuple(transformed_box((xs[0], ys[0], xs[-1], ys[-1]), point_map)),
            f"ocr-{engine}",
            confidence,
            boxes,
            row_indices,
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
                    record["confidence"] = (
                        min((word["confidence"] for word in grid[header_index][c]), default=0)
                        if header_index is not None
                        else None
                    )
            if alternate and engine == "tesseract" and header_index is not None:
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
                    table.cell_confidence[(r, c)] = min(
                        (word["confidence"] for word in cell), default=0
                    )
                    for record in table.cell_sources[r][c]:
                        record["confidence"] = table.cell_confidence[(r, c)]
                        record["initial_reading"] = original_readings[raw_index][c]
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
                            readings = recognize(footer, engine)
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
