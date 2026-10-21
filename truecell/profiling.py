"""Fast, deterministic page profiling used to choose extraction strategies.

The profiler never interprets or changes document values.  It records enough
evidence to explain why native extraction, OCR, or an independent cross-check
was selected for a page.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any

import cv2
import fitz
import numpy as np
from PIL import Image

LANGUAGE_ALIASES = {
    "en": "eng",
    "english": "eng",
    "hi": "hin",
    "hindi": "hin",
    "te": "tel",
    "telugu": "tel",
    "ta": "tam",
    "tamil": "tam",
    "kn": "kan",
    "kannada": "kan",
    "ml": "mal",
    "malayalam": "mal",
    "bn": "ben",
    "bengali": "ben",
    "gu": "guj",
    "gujarati": "guj",
    "mr": "mar",
    "marathi": "mar",
    "pa": "pan",
    "punjabi": "pan",
    "ur": "urd",
    "urdu": "urd",
    "ar": "ara",
    "arabic": "ara",
}


@dataclass(frozen=True)
class PageProfile:
    """Serializable routing evidence for one source page."""

    content_mode: str
    native_text_health: str
    native_word_count: int
    native_character_count: int
    replacement_character_ratio: float
    printable_character_ratio: float
    overlapping_word_ratio: float
    image_count: int
    image_coverage: float
    raster_profiled: bool
    ink_coverage: float
    blur_score: float
    contrast_score: float
    skew_degrees: float
    rotation_hint: int
    perspective_risk: float
    table_likelihood: float
    estimated_tables: int
    table_count_class: str
    quality_grade: str
    content_cues: list[str] = field(default_factory=list)
    detected_scripts: list[str] = field(default_factory=list)
    requested_ocr_languages: list[str] = field(default_factory=list)
    recommended_strategy: str = "native"
    cross_check_recommended: bool = False
    high_value_content: bool = False
    risk_reasons: list[str] = field(default_factory=list)
    profiler_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_languages(value: str | Iterable[str] | None) -> tuple[str, ...]:
    """Normalize user-friendly OCR language names to Tesseract codes."""
    if value is None:
        return ("eng",)
    pieces = re.split(r"[,+;\s]+", value) if isinstance(value, str) else list(value)
    output: list[str] = []
    for piece in pieces:
        token = str(piece).strip().lower().replace("-", "_")
        if not token:
            continue
        token = LANGUAGE_ALIASES.get(token, token)
        if not re.fullmatch(r"[a-z]{3}(?:_[a-z0-9]+)?", token):
            raise ValueError(f"Invalid OCR language code: {piece!r}.")
        if token not in output:
            output.append(token)
    return tuple(output or ["eng"])


def detect_scripts(text: str) -> list[str]:
    """Identify scripts present in native text without language guessing."""
    ranges = {
        "Latin": ((0x0041, 0x024F),),
        "Devanagari": ((0x0900, 0x097F),),
        "Bengali": ((0x0980, 0x09FF),),
        "Gurmukhi": ((0x0A00, 0x0A7F),),
        "Gujarati": ((0x0A80, 0x0AFF),),
        "Tamil": ((0x0B80, 0x0BFF),),
        "Telugu": ((0x0C00, 0x0C7F),),
        "Kannada": ((0x0C80, 0x0CFF),),
        "Malayalam": ((0x0D00, 0x0D7F),),
        "Arabic": ((0x0600, 0x06FF), (0x0750, 0x077F)),
        "Cyrillic": ((0x0400, 0x052F),),
        "CJK": ((0x3400, 0x9FFF),),
    }
    counts = {name: 0 for name in ranges}
    for character in text:
        point = ord(character)
        if not character.isalpha():
            continue
        for name, spans in ranges.items():
            if any(start <= point <= end for start, end in spans):
                counts[name] += 1
                break
    return [name for name, count in counts.items() if count >= 2]


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _render_preview(page: fitz.Page, dpi: int = 96) -> Image.Image:
    """Render a bounded preview; full-resolution OCR remains a separate step."""
    width, height = max(1.0, page.rect.width), max(1.0, page.rect.height)
    limit = min(2200 * 72 / max(width, height), math.sqrt(3_000_000 / (width * height)) * 72)
    actual = max(36, min(dpi, int(limit)))
    pix = page.get_pixmap(dpi=actual, colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def _line_and_table_signals(gray: np.ndarray) -> tuple[float, float, int, float, int]:
    """Return skew, perspective risk, table count, likelihood and rotation hint."""
    h, w = gray.shape
    if h < 20 or w < 20:
        return 0.0, 0.0, 0, 0.0, 0
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12
    )
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 360,
        threshold=max(30, min(h, w) // 18),
        minLineLength=max(25, min(h, w) // 14),
        maxLineGap=max(8, min(h, w) // 80),
    )
    horizontal_angles: list[float] = []
    horizontal_weight = vertical_weight = 0.0
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            length = math.hypot(x2 - x1, y2 - y1)
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            folded = ((angle + 90) % 180) - 90
            if abs(folded) <= 15:
                horizontal_angles.append(folded)
                horizontal_weight += length
            elif abs(abs(folded) - 90) <= 15:
                vertical_weight += length
    skew = float(median(horizontal_angles)) if len(horizontal_angles) >= 3 else 0.0
    rotation_hint = 90 if vertical_weight > horizontal_weight * 2.5 and vertical_weight > w else 0

    horizontal = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, w // 35), 1)),
    )
    vertical = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(25, h // 35))),
    )
    line_mask = cv2.bitwise_or(horizontal, vertical)
    connected = cv2.dilate(line_mask, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    table_regions = 0
    for contour in contours:
        _, _, rw, rh = cv2.boundingRect(contour)
        if rw >= w * 0.18 and rh >= h * 0.035:
            table_regions += 1
    intersections = cv2.countNonZero(cv2.bitwise_and(horizontal, vertical))
    rule_coverage = cv2.countNonZero(line_mask) / max(1, gray.size)
    likelihood = _clamp(table_regions * 0.28 + intersections / 180 + rule_coverage * 9)

    perspective = 0.0
    large = [c for c in contours if cv2.contourArea(c) > gray.size * 0.04]
    if large:
        hull = cv2.convexHull(np.concatenate(large))
        quad = cv2.approxPolyDP(hull, 0.025 * cv2.arcLength(hull, True), True)
        if len(quad) == 4:
            points = quad.reshape(4, 2).astype(float)
            centre = points.mean(axis=0)
            points = np.array(
                sorted(points, key=lambda p: math.atan2(p[1] - centre[1], p[0] - centre[0]))
            )
            lengths = [float(np.linalg.norm(points[(i + 1) % 4] - points[i])) for i in range(4)]
            if min(lengths) > 10:
                perspective = _clamp(
                    max(
                        abs(lengths[0] - lengths[2]) / max(lengths[0], lengths[2]),
                        abs(lengths[1] - lengths[3]) / max(lengths[1], lengths[3]),
                    )
                    * 3
                )
    return round(skew, 2), perspective, table_regions, likelihood, rotation_hint


def _raster_signals(image: Image.Image) -> dict[str, float | int]:
    gray = np.asarray(image.convert("L"))
    if max(gray.shape) > 1800:
        scale = 1800 / max(gray.shape)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ink = gray < 245
    ink_coverage = float(np.count_nonzero(ink) / max(1, gray.size))
    if np.count_nonzero(ink):
        foreground = gray[ink]
        contrast = float(np.median(gray) - np.percentile(foreground, 25)) / 220
    else:
        contrast = 0.0
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    edge_pixels = np.abs(laplacian)[ink] if np.count_nonzero(ink) else np.array([])
    sharpness = float(np.percentile(edge_pixels, 75)) if edge_pixels.size else 0.0
    blur_score = _clamp(sharpness / 75)
    skew, perspective, tables, table_likelihood, rotation_hint = _line_and_table_signals(gray)
    return {
        "ink_coverage": _clamp(ink_coverage),
        "contrast_score": _clamp(contrast),
        "blur_score": blur_score,
        "skew_degrees": skew,
        "perspective_risk": perspective,
        "estimated_tables": tables,
        "table_likelihood": table_likelihood,
        "rotation_hint": rotation_hint,
    }


def _overlap_ratio(words: list[tuple]) -> float:
    """Detect duplicate/garbled text layers made of overlapping words."""
    if len(words) < 2:
        return 0.0
    ordered = sorted(words, key=lambda word: (round(word[1], 1), word[0]))[:1000]
    overlaps = 0
    comparisons = 0
    for previous, current in zip(ordered, ordered[1:]):
        if abs(float(previous[1]) - float(current[1])) > 3:
            continue
        comparisons += 1
        x0, x1 = max(previous[0], current[0]), min(previous[2], current[2])
        union = max(previous[2], current[2]) - min(previous[0], current[0])
        if union > 0 and max(0, x1 - x0) / union > 0.65:
            overlaps += 1
    return _clamp(overlaps / max(1, comparisons))


def _image_coverage(page: fitz.Page) -> tuple[int, float]:
    try:
        records = page.get_image_info()
    except (RuntimeError, ValueError):
        return len(page.get_images()), 0.0
    area = max(1.0, page.rect.width * page.rect.height)
    covered = 0.0
    for record in records:
        bbox = fitz.Rect(record.get("bbox", (0, 0, 0, 0))) & page.rect
        covered += max(0.0, bbox.width) * max(0.0, bbox.height)
    return len(records), _clamp(covered / area)


def _content_cues(text: str, table_likelihood: float) -> tuple[list[str], bool]:
    lowered = text.lower()
    cues: list[str] = []
    keyword_sets = {
        "invoice": ("invoice", "tax invoice", "bill to", "invoice no"),
        "statement": ("statement", "opening balance", "closing balance", "debit", "credit"),
        "form": ("application form", "signature", "declaration", "date of birth"),
    }
    for cue, keywords in keyword_sets.items():
        if any(keyword in lowered for keyword in keywords):
            cues.append(cue)
    if table_likelihood >= 0.35:
        cues.append("table")
    if not cues and text.strip():
        cues.append("ordinary_text")
    high_value_words = (
        "amount",
        "total",
        "balance",
        "account",
        "invoice",
        "tax",
        "salary",
        "price",
        "quantity",
        "transaction",
        "debit",
        "credit",
    )
    high_value = any(re.search(rf"\b{word}\b", lowered) for word in high_value_words)
    return cues, high_value


def profile_page(page: fitz.Page, languages: str | Iterable[str] | None = None) -> PageProfile:
    """Profile one page without trusting native text or invoking an OCR engine."""
    requested = normalize_languages(languages)
    warnings: list[str] = []
    try:
        words = list(page.get_text("words", sort=True))
    except (RuntimeError, ValueError) as exc:
        words = []
        warnings.append(f"native_text_probe:{type(exc).__name__}")
    text = " ".join(str(word[4]) for word in words)
    characters = len(text)
    replacement_ratio = text.count("\ufffd") / max(1, characters)
    printable = sum(
        character.isprintable() and not unicodedata.category(character).startswith("C")
        for character in text
    )
    printable_ratio = printable / max(1, characters)
    overlap = _overlap_ratio(words)
    usable = sum(character.isalnum() for character in text)
    if len(words) >= 8 and usable >= 30:
        if replacement_ratio <= 0.005 and printable_ratio >= 0.98 and overlap < 0.2:
            text_health = "healthy"
        elif replacement_ratio <= 0.03 and printable_ratio >= 0.92 and overlap < 0.45:
            text_health = "marginal"
        else:
            text_health = "damaged"
    elif words:
        text_health = (
            "marginal" if replacement_ratio <= 0.02 and printable_ratio >= 0.95 else "damaged"
        )
    else:
        text_health = "missing"

    image_count, image_coverage = _image_coverage(page)
    # A healthy native page without a substantial image cannot be blurred or
    # photographed: rasterizing it solely to rediscover sharp vector text adds
    # material cost on long PDFs. Scans, hybrids and uncertain text layers keep
    # the full visual-quality probe.
    raster_profiled = not (text_health == "healthy" and image_coverage < 0.2 and page.rotation == 0)
    try:
        raster = (
            _raster_signals(_render_preview(page))
            if raster_profiled
            else {
                "ink_coverage": 0.0,
                "contrast_score": 1.0,
                "blur_score": 1.0,
                "skew_degrees": 0.0,
                "perspective_risk": 0.0,
                "estimated_tables": 0,
                "table_likelihood": 0.0,
                "rotation_hint": 0,
            }
        )
    except (RuntimeError, ValueError, MemoryError, cv2.error) as exc:
        warnings.append(f"raster_probe:{type(exc).__name__}")
        raster_profiled = False
        raster = {
            "ink_coverage": 0.0,
            "contrast_score": 0.0,
            "blur_score": 0.0,
            "skew_degrees": 0.0,
            "perspective_risk": 0.0,
            "estimated_tables": 0,
            "table_likelihood": 0.0,
            "rotation_hint": 0,
        }
    if page.rotation in {90, 180, 270}:
        raster["rotation_hint"] = page.rotation

    native_alignment = 0.0
    if len(words) >= 6:
        x_bins: dict[int, int] = {}
        for word in words:
            key = round(float(word[0]) / max(4.0, page.rect.width / 80))
            x_bins[key] = x_bins.get(key, 0) + 1
        aligned = sum(count for count in x_bins.values() if count >= 3)
        native_alignment = min(1.0, aligned / max(1, len(words)))
    table_likelihood = max(float(raster["table_likelihood"]), native_alignment * 0.75)
    estimated_tables = int(raster["estimated_tables"])
    if not estimated_tables and table_likelihood >= 0.35:
        estimated_tables = 1
    cues, high_value = _content_cues(text, table_likelihood)
    scripts = detect_scripts(text)

    if not words and not image_count and float(raster["ink_coverage"]) < 0.0015:
        content_mode = "empty"
    elif text_health == "healthy" and image_coverage < 0.55:
        content_mode = "digital"
    elif text_health == "healthy":
        content_mode = "hybrid"
    elif words:
        content_mode = "damaged_text_layer" if text_health == "damaged" else "hybrid"
    else:
        content_mode = "scan"

    risks: list[str] = []
    if text_health in {"marginal", "damaged"}:
        risks.append(f"{text_health}_native_text")
    if float(raster["ink_coverage"]) >= 0.003 and float(raster["contrast_score"]) < 0.25:
        risks.append("low_contrast")
    if float(raster["ink_coverage"]) >= 0.003 and float(raster["blur_score"]) < 0.16:
        risks.append("blur")
    if abs(float(raster["skew_degrees"])) >= 1.0:
        risks.append("skew")
    if int(raster["rotation_hint"]):
        risks.append("rotation")
    if float(raster["perspective_risk"]) >= 0.25:
        risks.append("perspective")
    if len(scripts) > 1:
        risks.append("mixed_scripts")

    severe_risks = {"damaged_native_text", "rotation", "perspective"}
    if severe_risks.intersection(risks) or len(risks) >= 3:
        quality_grade = "poor"
    elif risks:
        quality_grade = "review"
    else:
        quality_grade = "good"

    quality_risk = any(
        reason in risks for reason in ("low_contrast", "blur", "skew", "rotation", "perspective")
    )
    cross_check = text_health in {"marginal", "damaged"} or (
        high_value and table_likelihood >= 0.35 and (quality_risk or image_coverage >= 0.2)
    )
    if content_mode == "empty":
        strategy = "empty"
    elif text_health == "missing":
        strategy = "ocr"
    elif cross_check:
        strategy = "native-ocr-cross-check"
    else:
        strategy = "native"

    return PageProfile(
        content_mode=content_mode,
        native_text_health=text_health,
        native_word_count=len(words),
        native_character_count=characters,
        replacement_character_ratio=round(replacement_ratio, 4),
        printable_character_ratio=round(printable_ratio, 4),
        overlapping_word_ratio=overlap,
        image_count=image_count,
        image_coverage=image_coverage,
        raster_profiled=raster_profiled,
        ink_coverage=float(raster["ink_coverage"]),
        blur_score=float(raster["blur_score"]),
        contrast_score=float(raster["contrast_score"]),
        skew_degrees=float(raster["skew_degrees"]),
        rotation_hint=int(raster["rotation_hint"]),
        perspective_risk=float(raster["perspective_risk"]),
        table_likelihood=round(table_likelihood, 3),
        estimated_tables=estimated_tables,
        table_count_class=(
            "multiple" if estimated_tables > 1 else "single" if estimated_tables == 1 else "none"
        ),
        quality_grade=quality_grade,
        content_cues=cues,
        detected_scripts=scripts,
        requested_ocr_languages=list(requested),
        recommended_strategy=strategy,
        cross_check_recommended=cross_check,
        high_value_content=high_value,
        risk_reasons=risks,
        profiler_warnings=warnings,
    )
