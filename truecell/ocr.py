"""Offline OCR, arbitrary small-angle deskew, grid geometry and word-box alignment."""
from __future__ import annotations

from functools import lru_cache
import importlib.util
from pathlib import Path
import shutil
from statistics import median
import math

import cv2
import numpy as np
from PIL import Image

from .models import Table
from .table import normalize, words_to_grid


def tesseract_path() -> str | None:
    """Locate the system binary, including common Windows installations."""
    found = shutil.which("tesseract")
    if found:
        return found
    candidate = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    return str(candidate) if candidate.is_file() else None


def available_engines() -> list[str]:
    """List installed offline engines without downloading or loading a model."""
    engines = []
    if importlib.util.find_spec("rapidocr_onnxruntime"):
        engines.append("rapidocr")
    if importlib.util.find_spec("pytesseract") and tesseract_path():
        engines.append("tesseract")
    return engines


@lru_cache(maxsize=1)
def rapid_engine():
    """Lazily load bundled ONNX models with bounded CPU threading."""
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)


def preprocess(image: Image.Image, alternate: bool = False) -> tuple[np.ndarray, float]:
    """Denoise, improve contrast and deskew using a robust median Hough angle."""
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    if max(gray.shape) > 5500:
        scale = 5500 / max(gray.shape)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    small_scale = min(1, 1600 / max(gray.shape))
    small = cv2.resize(gray, None, fx=small_scale, fy=small_scale)
    edges = cv2.Canny(small, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 1800, threshold=60,
                            minLineLength=max(40, small.shape[1] // 12), maxLineGap=20)
    angles = []
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            angle = math.degrees(math.atan2(y2-y1, x2-x1))
            if abs(angle) <= 15:
                angles.append(angle)
    angle = median(angles) if len(angles) >= 3 else 0.0
    if abs(angle) > .15:
        h, w = gray.shape
        matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
        gray = cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)
    gray = cv2.medianBlur(gray, 3)
    if alternate:
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 35, 13)
    else:
        gray = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(gray)
    return gray, angle


def _runs(indices: np.ndarray, gap: int = 3) -> list[int]:
    groups: list[list[int]] = []
    for index in indices.tolist():
        if groups and index - groups[-1][-1] <= gap:
            groups[-1].append(index)
        else:
            groups.append([index])
    return [round(float(np.mean(g))) for g in groups]


def grid_regions(gray: np.ndarray) -> tuple[list[tuple[list[int], list[int]]], np.ndarray]:
    """Find individual ruled table regions and create a line-removal mask."""
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = gray.shape
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_RECT, (max(35, w//35), 1)))
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, h//35))))
    mask = cv2.bitwise_or(horizontal, vertical)
    connected = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for contour in contours:
        x, y, rw, rh = cv2.boundingRect(contour)
        if rw < w * .15 or rh < 40:
            continue
        crop_v = vertical[y:y+rh, x:x+rw]
        crop_h = horizontal[y:y+rh, x:x+rw]
        xs = [x + c for c in _runs(np.where(np.count_nonzero(crop_v, axis=0) > rh * .35)[0])]
        ys = [y + r for r in _runs(np.where(np.count_nonzero(crop_h, axis=1) > rw * .35)[0])]
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
            words.append({"x0": float(points[:, 0].min()), "x1": float(points[:, 0].max()),
                          "top": float(points[:, 1].min()), "bottom": float(points[:, 1].max()),
                          "text": text, "confidence": float(confidence)})
        return words
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = tesseract_path() or "tesseract"
    data = pytesseract.image_to_data(gray, config="--psm 6", output_type=pytesseract.Output.DICT, timeout=90)
    return [{"x0": data["left"][i], "x1": data["left"][i] + data["width"][i],
             "top": data["top"][i], "bottom": data["top"][i] + data["height"][i],
             "text": text, "confidence": max(0, float(data["conf"][i])) / 100}
            for i, text in enumerate(data["text"]) if text.strip()]


def extract_image(image: Image.Image, page: int, engine: str = "rapidocr", *,
                  alternate: bool = False, rotation: int = 0) -> list[Table]:
    """Reconstruct ruled grids first; fall back to recurring word-box alignment."""
    if rotation:
        image = image.rotate(rotation, expand=True, fillcolor="white")
    gray, angle = preprocess(image, alternate)
    regions, mask = grid_regions(gray)
    cleaned = gray.copy()
    # Thin rules are whitened; broad dark header fills are retained.
    cleaned[cv2.dilate(mask, np.ones((2, 2), np.uint8)) > 0] = 255
    words = recognize(cleaned, engine)
    confidence = median(w["confidence"] for w in words) if words else 0
    h, w = gray.shape
    sx, sy = image.width * 72 / 300 / w, image.height * 72 / 300 / h
    tables = []
    for xs, ys in regions:
        grid = [[[] for _ in range(len(xs)-1)] for _ in range(len(ys)-1)]
        for word in words:
            cx, cy = (word["x0"]+word["x1"])/2, (word["top"]+word["bottom"])/2
            c = next((i for i in range(len(xs)-1) if xs[i] <= cx < xs[i+1]), None)
            r = next((i for i in range(len(ys)-1) if ys[i] <= cy < ys[i+1]), None)
            if r is not None and c is not None:
                grid[r][c].append(word)
        raw = [[" ".join(word["text"] for word in sorted(cell, key=lambda v: (v["top"], v["x0"])))
                for cell in row] for row in grid]
        table = normalize(raw, page, (xs[0]*sx, ys[0]*sy, xs[-1]*sx, ys[-1]*sy),
                          f"ocr-{engine}", confidence)
        if table:
            offset = len(raw) - len(table.rows)
            for r, row in enumerate(grid[offset:]):
                for c, cell in enumerate(row):
                    table.cell_confidence[(r, c)] = min((word["confidence"] for word in cell), default=0)
            table.notes.append(f"OCR {engine}; deskew correction {angle:.2f} degrees; values require source review.")
            tables.append(table)
    if not tables:
        scaled = [{**word, "x0": word["x0"]*sx, "x1": word["x1"]*sx,
                   "top": word["top"]*sy, "bottom": word["bottom"]*sy} for word in words]
        tables = words_to_grid(scaled, page, f"ocr-{engine}-words", w*sx, h*sy)
        for table in tables:
            table.confidence = min(confidence, .72)
    return tables
