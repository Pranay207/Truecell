"""Image geometry and engine-independent OCR reconstruction regressions."""

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from truecell.ocr import (
    cell_text,
    extract_image,
    grid_regions,
    preprocess,
    rectify_perspective,
)


def make_grid():
    image = Image.new("RGB", (900, 500), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 840, 110), fill=(25, 50, 75))
    for x in [40, 240, 440, 640, 840]:
        draw.line((x, 40, x, 390), fill=(145, 160, 175), width=3)
    for y in [40, 110, 180, 250, 320, 390]:
        draw.line((40, y, 840, y), fill=(145, 160, 175), width=3)
    return image


def test_pale_grid_survives_dark_header():
    gray = cv2.cvtColor(np.asarray(make_grid()), cv2.COLOR_RGB2GRAY)
    regions, _ = grid_regions(gray)
    assert len(regions) == 1
    assert len(regions[0][0]) == 5 and len(regions[0][1]) == 6


def test_white_header_letters_do_not_create_extra_grid_rows():
    image = make_grid()
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=28)
    for x, label in zip([55, 255, 455, 655], ["Record", "Description", "Units", "Amount"]):
        draw.text((x, 60), label, font=font, fill="white")
    regions, _ = grid_regions(np.asarray(image.convert("L")))
    assert len(regions) == 1
    assert len(regions[0][1]) == 6
    assert abs(regions[0][1][0] - 40) < 5
    assert abs(regions[0][1][1] - 110) < 5


@pytest.mark.parametrize("angle", [-7, -3, 3, 7])
def test_deskew_arbitrary_angle(angle):
    image = make_grid().rotate(angle, fillcolor="white", resample=Image.Resampling.BICUBIC)
    _, correction = preprocess(image)
    assert abs(abs(correction) - abs(angle)) < 1


def test_grid_box_assignment_preserves_empty_cell(monkeypatch):
    import truecell.ocr as ocr

    words = []
    rows = [
        ["Code", "Label", "Units", "Value"],
        ["A", "Item", "2", "10"],
        ["B", "Other", "", "15"],
        ["C", "Third", "4", "20"],
        ["D", "Last", "5", "25"],
    ]
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if value:
                words.append(
                    {
                        "x0": 60 + c * 200,
                        "x1": 130 + c * 200,
                        "top": 60 + r * 70,
                        "bottom": 80 + r * 70,
                        "text": value,
                        "confidence": 0.99,
                    }
                )
    monkeypatch.setattr(ocr, "recognize", lambda gray, engine: words)
    tables = extract_image(make_grid(), 1, "test")
    assert tables[0].headers == rows[0]
    assert tables[0].rows[1] == rows[2]


def test_blank_image_no_invented_table(monkeypatch):
    import truecell.ocr as ocr

    monkeypatch.setattr(ocr, "recognize", lambda gray, engine: [])
    assert extract_image(Image.new("RGB", (500, 300), "white"), 1, "test") == []


def test_blank_grid_row_does_not_shift_ocr_scores_or_original_readings(monkeypatch):
    import truecell.ocr as ocr

    rows = [
        ["Code", "Label", "Units", "Value"],
        ["A", "Item", "2", "10"],
        ["", "", "", ""],
        ["B", "Other", "3", "15"],
        ["C", "Third", "4", "20"],
    ]
    words = [
        {
            "x0": 60 + c * 200,
            "x1": 130 + c * 200,
            "top": 60 + r * 70,
            "bottom": 80 + r * 70,
            "text": value,
            "confidence": 0.91 + r * 0.01,
        }
        for r, row in enumerate(rows)
        for c, value in enumerate(row)
        if value
    ]
    monkeypatch.setattr(ocr, "recognize", lambda gray, engine: words)
    table = extract_image(make_grid(), 1, "test")[0]
    assert table.rows == [rows[1], rows[3], rows[4]]
    assert table.cell_confidence[0, 0] == pytest.approx(0.92)
    assert table.cell_confidence[1, 0] == pytest.approx(0.94)
    assert table.cell_sources[0][0][0]["initial_reading"] == "A"
    assert table.cell_sources[1][0][0]["initial_reading"] == "B"
    assert table.header_sources[0][0]["confidence"] == pytest.approx(0.91)


def test_filtered_footer_cannot_be_used_as_the_header_reading(monkeypatch):
    import truecell.ocr as ocr

    rows = [
        ["Code", "Label", "Units", "Value"],
        ["Page 1 of 2", "", "", ""],
        ["A", "Item", "2", "10"],
        ["B", "Other", "3", "15"],
        ["C", "Third", "4", "20"],
    ]
    words = [
        {
            "x0": 60 + c * 200,
            "x1": 130 + c * 200,
            "top": 60 + r * 70,
            "bottom": 80 + r * 70,
            "text": value,
            "confidence": 0.91 + r * 0.01,
        }
        for r, row in enumerate(rows)
        for c, value in enumerate(row)
        if value
    ]
    monkeypatch.setattr(ocr, "recognize", lambda gray, engine: words)
    table = extract_image(make_grid(), 1, "test")[0]
    assert table.headers == rows[0]
    assert table.rows == rows[2:]
    assert table.header_sources[0][0]["confidence"] == pytest.approx(0.91)
    assert table.cell_sources[0][0][0]["initial_reading"] == "A"


def test_box_jitter_does_not_reorder_words():
    words = [
        {"x0": 50, "x1": 80, "top": 10, "bottom": 25, "text": "model"},
        {"x0": 10, "x1": 45, "top": 11, "bottom": 26, "text": "Widget"},
        {"x0": 90, "x1": 99, "top": 9, "bottom": 24, "text": "4"},
    ]
    assert cell_text(words) == "Widget model 4"


def test_rectangular_grid_not_rectified_unnecessarily():
    _, quad = rectify_perspective(make_grid())
    assert quad is None


def test_perspective_grid_detected():
    image = np.asarray(make_grid())
    matrix = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [900, 0], [900, 500], [0, 500]]),
        np.float32([[50, 30], [840, 0], [900, 450], [0, 500]]),
    )
    warped = Image.fromarray(
        cv2.warpPerspective(image, matrix, (900, 500), borderValue=(255, 255, 255))
    )
    _, quad = rectify_perspective(warped)
    assert quad is not None


def test_uncertain_large_grid_retries_rotation(tmp_path, monkeypatch):
    import truecell.ocr as ocr
    from truecell.models import Table
    from truecell.pipeline import convert

    source = tmp_path / "sideways.png"
    make_grid().save(source)
    rotations = []

    def extract(image, page, engine, *, rotation=0, **options):
        rotations.append(rotation)
        return [
            Table(
                ["Ref", "Units", "Amount"]
                if rotation == 90
                else ["Column 1", "Column 2", "Column 3"],
                [[f"A{i}", str(i + 1), str((i + 1) * 5)] for i in range(8)],
                page,
                (0, 0, 100, 100),
                "ocr-test",
                0.99 if rotation == 90 else 0.5,
                header_detected=rotation == 90,
            )
        ]

    monkeypatch.setattr(ocr, "available_engines", lambda: ["test"])
    monkeypatch.setattr(ocr, "extract_image", extract)
    result = convert(source)
    assert 90 in rotations
    assert result.tables[0].headers == ["Ref", "Units", "Amount"]
    assert next(a for a in result.pages[0].attempts if a.selected).strategy == "rotate-90"


def test_uncertain_rotated_reading_gets_independent_engine(tmp_path, monkeypatch):
    import truecell.ocr as ocr
    from truecell.models import Table
    from truecell.pipeline import convert

    source = tmp_path / "rotated.png"
    make_grid().save(source)

    def extract(image, page, engine, *, rotation=0, **options):
        upright = rotation == 270
        good = upright and engine == "second"
        table = Table(
            ["Ref", "Units", "Amount"] if upright else ["Column 1", "Column 2", "Column 3"],
            [[f"A{i}", str(i + 1), str((i + 1) * 5)] for i in range(8)],
            page,
            (0, 0, 100, 100),
            "ocr-test",
            0.99 if good else 0.5,
            header_detected=upright,
        )
        if not good:
            table.cell_confidence[0, 0] = 0.1
        return [table]

    monkeypatch.setattr(ocr, "available_engines", lambda: ["first", "second"])
    monkeypatch.setattr(ocr, "extract_image", extract)
    result = convert(source)
    selected = next(a for a in result.pages[0].attempts if a.selected)
    assert selected.engine == "second" and selected.strategy == "rotate-270-second-engine"
