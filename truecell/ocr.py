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


def cell_text(words: list[dict]) -> str:
    """Read words in lines without letting one-pixel box jitter reorder a cell."""
    lines: list[list[dict]] = []
    height = median(w["bottom"]-w["top"] for w in words) if words else 10
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"]-median(w["top"] for w in lines[-1])) < height*.55:
            lines[-1].append(word)
        else:
            lines.append([word])
    return " ".join(w["text"] for line in lines for w in sorted(line,key=lambda w:w["x0"]))


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
    if importlib.util.find_spec("pytesseract") and tesseract_path():
        engines.append("tesseract")
    if importlib.util.find_spec("rapidocr_onnxruntime"):
        engines.append("rapidocr")
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


def rectify_perspective(image: Image.Image) -> tuple[Image.Image, tuple | None]:
    """Rectify a dominant quadrilateral table only when opposing edges diverge."""
    gray = np.asarray(image.convert("L"))
    scale = min(1, 1600 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale)
    binary = cv2.adaptiveThreshold(small,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,35,12)
    binary = cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_ = cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    large = [c for c in contours if cv2.contourArea(c) > small.size*.02]
    if not large:
        return image, None
    hull = cv2.convexHull(np.concatenate(large))
    quad = cv2.approxPolyDP(hull,.025*cv2.arcLength(hull,True),True)
    if len(quad) != 4 or cv2.contourArea(quad) < small.size*.12:
        return image, None
    points = quad.reshape(4,2).astype(np.float32)/scale
    ordered = np.zeros((4,2),np.float32)
    sums, differences = points.sum(axis=1), np.diff(points,axis=1).ravel()
    ordered[0], ordered[2] = points[np.argmin(sums)],points[np.argmax(sums)]
    ordered[1], ordered[3] = points[np.argmin(differences)],points[np.argmax(differences)]
    top,right,bottom,left = [float(np.linalg.norm(ordered[(i+1)%4]-ordered[i])) for i in range(4)]
    if min(top,right,bottom,left)<30 or max(abs(top-bottom)/max(top,bottom),abs(left-right)/max(left,right))<.02:
        return image, None
    width,height = round(max(top,bottom)),round(max(left,right))
    destination = np.float32([[0,0],[width-1,0],[width-1,height-1],[0,height-1]])
    matrix = cv2.getPerspectiveTransform(ordered,destination)
    transformed = cv2.warpPerspective(np.asarray(image.convert("RGB")),matrix,(width,height),borderValue=(255,255,255))
    transformed = cv2.copyMakeBorder(transformed,20,20,20,20,cv2.BORDER_CONSTANT,value=(255,255,255))
    result = Image.fromarray(transformed)
    result.info.update(image.info)
    return result, (float(points[:,0].min()),float(points[:,1].min()),float(points[:,0].max()),float(points[:,1].max()))


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
    # Global Otsu can discard pale gray ruling when a dark header dominates.
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 35, 12)
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
    mode = 7 if engine == "tesseract-cell" else 6
    data = pytesseract.image_to_data(gray, config=f"--psm {mode}", output_type=pytesseract.Output.DICT, timeout=90)
    return [{"x0": data["left"][i], "x1": data["left"][i] + data["width"][i],
             "top": data["top"][i], "bottom": data["top"][i] + data["height"][i],
             "text": text, "confidence": max(0, float(data["conf"][i])) / 100}
            for i, text in enumerate(data["text"]) if text.strip()]


def extract_image(image: Image.Image, page: int, engine: str = "rapidocr", *,
                  alternate: bool = False, rotation: int = 0, perspective: bool = False) -> list[Table]:
    """Reconstruct ruled grids first; fall back to recurring word-box alignment."""
    if rotation:
        image = image.rotate(rotation, expand=True, fillcolor="white")
    source_quad = None
    if perspective:
        image, source_quad = rectify_perspective(image)
    gray, angle = preprocess(image, False)
    regions, mask = grid_regions(gray)
    cleaned = gray.copy()
    # Whiten inferred rule coordinates, not the entire morphology mask: the
    # latter can erase filled header backgrounds and the text they surround.
    for xs, ys in regions:
        # OCR engines struggle with white text on dark, filled header bands.
        for y0, y1 in zip(ys, ys[1:]):
            band = cleaned[y0+4:y1-3, xs[0]+4:xs[-1]-3]
            if band.size and np.median(band) < 150:
                cleaned[y0+4:y1-3, xs[0]+4:xs[-1]-3] = 255 - band
        for x in xs:
            cv2.line(cleaned, (x, ys[0]), (x, ys[-1]), 255, 7)
        for y in ys:
            cv2.line(cleaned, (xs[0], y), (xs[-1], y), 255, 7)
    if alternate and engine != "tesseract":
        # Normalize dark backgrounds before binarization to preserve header text.
        cleaned = cv2.adaptiveThreshold(cleaned, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 35, 13)
    if source_quad:
        # A white rule painted across a shaded photograph becomes a false edge.
        # Remove the slowly varying illumination before OCR layout analysis.
        cleaned = cv2.divide(cleaned,cv2.GaussianBlur(cleaned,(0,0),25),scale=255)
    words = recognize(cleaned, engine)
    confidence = median(w["confidence"] for w in words) if words else 0
    h, w = gray.shape
    dpi_x, dpi_y = image.info.get("dpi", (300, 300))
    sx, sy = image.width * 72 / dpi_x / w, image.height * 72 / dpi_y / h
    tables = []
    for xs, ys in regions:
        grid = [[[] for _ in range(len(xs)-1)] for _ in range(len(ys)-1)]
        for word in words:
            cx, cy = (word["x0"]+word["x1"])/2, (word["top"]+word["bottom"])/2
            c = next((i for i in range(len(xs)-1) if xs[i] <= cx < xs[i+1]), None)
            r = next((i for i in range(len(ys)-1) if ys[i] <= cy < ys[i+1]), None)
            if r is not None and c is not None:
                grid[r][c].append(word)
        rechecks = []
        if alternate and engine == "tesseract":
            for r, row in enumerate(grid):
                for c, cell in enumerate(row):
                    if cell and min(word["confidence"] for word in cell) < .80:
                        crop = cleaned[ys[r]+5:ys[r+1]-4, xs[c]+5:xs[c+1]-4]
                        if not crop.size:
                            continue
                        rechecked = recognize(cv2.copyMakeBorder(crop,12,12,12,12,cv2.BORDER_CONSTANT,value=255), "tesseract-cell")
                        if rechecked and min(w["confidence"] for w in rechecked) > min(w["confidence"] for w in cell):
                            old, new = cell_text(cell), cell_text(rechecked)
                            if old != new:
                                rechecks.append(f"Cell recheck at grid row {r+1}, column {c+1}: {old!r} -> {new!r}; compare source.")
                            grid[r][c] = rechecked
        raw = [[cell_text(cell) for cell in row] for row in grid]
        table = normalize(raw, page, (xs[0]*sx, ys[0]*sy, xs[-1]*sx, ys[-1]*sy),
                          f"ocr-{engine}", confidence)
        if table:
            offset = len(raw) - len(table.rows)
            for r, row in enumerate(grid[offset:]):
                for c, cell in enumerate(row):
                    table.cell_confidence[(r, c)] = min((word["confidence"] for word in cell), default=0)
            table.notes.append(f"OCR {engine}; deskew correction {angle:.2f} degrees; values require source review.")
            table.notes.extend(rechecks)
            tables.append(table)
    if not tables:
        scaled = [{**word, "x0": word["x0"]*sx, "x1": word["x1"]*sx,
                   "top": word["top"]*sy, "bottom": word["bottom"]*sy} for word in words]
        tables = words_to_grid(scaled, page, f"ocr-{engine}-words", w*sx, h*sy)
        for table in tables:
            table.confidence = min(confidence, .72)
    if source_quad:
        for table in tables:
            table.bbox = tuple(v*72/(dpi_x if i%2==0 else dpi_y) for i,v in enumerate(source_quad))
            table.notes.append("Perspective rectification inferred from a dominant table outline; verify row and column alignment.")
    return tables
