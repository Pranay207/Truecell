"""Layout and stitching regressions protect row counts and provenance."""

import pytest

from truecell.models import Table
from truecell.stitch import compatible, stitch
from truecell.table import normalize, words_to_grid


def t(page=1, headers=None, rows=None, bbox=(10, 10, 110, 100), detected=True):
    return Table(
        headers or ["ID", "Label", "Units", "Amt"],
        rows or [["A", "Item", "2", "10"]],
        page,
        bbox,
        "native",
        header_detected=detected,
    )


def test_split_row_keeps_both_sources():
    a = t(rows=[["A", "Long item", "", ""]])
    b = t(page=2, rows=[["", "continued", "3", "15"], ["B", "Next", "4", "20"]])
    joined, issues = stitch([a, b])
    assert joined[0].rows[0] == ["A", "Long item continued", "3", "15"]
    assert joined[0].provenance[0] == [(1, 1), (2, 1)]
    assert any(i.code == "split_row_join" for i in issues)


def test_split_row_preserves_low_confidence_of_continuation_cells():
    from truecell.validate import validate

    first = t(rows=[["A", "Long item", "", ""]])
    second = t(page=2, rows=[["", "continued", "3", "15"], ["B", "Next", "4", "20"]])
    second.engine = "ocr-test"
    second.row_engines = ["ocr-test"] * 2
    second.cell_confidence[0, 1] = 0.6
    second.cell_confidence[0, 2] = 0.7
    second.cell_confidence[1, 2] = 0.99
    joined, _ = stitch([first, second])
    table = joined[0]
    assert table.cell_confidence[0, 1] == 0.6
    assert table.cell_confidence[0, 2] == 0.7
    assert table.cell_confidence[1, 2] == 0.99
    assert any(i.code == "ocr_confidence" and i.row == 1 and i.column == 3 for i in validate(table))


@pytest.mark.parametrize(
    "page,headers,bbox,expected",
    [
        (2, None, (10, 10, 110, 100), True),
        (3, None, (10, 10, 110, 100), False),
        (1, None, (10, 10, 110, 100), False),
        (2, ["X", "Y"], (10, 10, 110, 100), False),
        (2, None, (60, 10, 160, 100), False),
        (2, ["a", "b", "c", "d"], (10, 10, 110, 100), False),
    ],
)
def test_join_guards(page, headers, bbox, expected):
    assert compatible(t(), t(page, headers, bbox=bbox)) == expected


def test_headerless_join_flagged():
    joined, issues = stitch([t(), t(page=2, detected=False)])
    assert len(joined) == 1
    assert issues[0].code == "inferred_join"


def test_two_tables_same_page_remain_separate():
    joined, _ = stitch([t(), t(bbox=(10, 200, 110, 300))])
    assert len(joined) == 2


def test_merged_headers_flattened():
    raw = [
        ["Product", None, "Movement", None],
        ["Code", "Name", "Units", "Value"],
        ["A", "Thing", "2", "10"],
        ["B", "Other", "3", "15"],
    ]
    found = normalize(raw, 1, (0, 0, 100, 100), "native")
    assert found.headers == [
        "Product | Code",
        "Product | Name",
        "Movement | Units",
        "Movement | Value",
    ]
    assert len(found.rows) == 2


def test_ragged_headers_are_extended_without_losing_spans():
    boxes = [
        [(0, 0, 100, 10)],
        [(0, 10, 50, 20), (50, 10, 100, 20)],
        [(0, 20, 50, 30), (50, 20, 100, 30)],
    ]
    merged = normalize(
        [["Group"], ["A", "B"], ["x", "1"]],
        1,
        (0, 0, 100, 100),
        "native-lines",
        cell_boxes=boxes,
    )
    assert merged.headers == ["Group | A", "Group | B"]
    assert merged.rows == [["x", "1"]]
    assert [source["text"] for source in merged.header_sources[1]] == ["Group", "B"]
    single = normalize(
        [["Item"], ["1", "10"], ["2", "20"]],
        1,
        (0, 0, 100, 100),
        "native-lines",
    )
    assert single.headers == ["Item", "Column 2"]
    assert single.rows == [["1", "10"], ["2", "20"]]


def test_ruled_vertical_group_cells_expand_with_original_evidence():
    raw = [
        ["Package", "Phase", "Line", "Amount"],
        ["WP-1", "Build", "1", "10"],
        [None, None, "1.1", "5"],
        [None, "QA", "2", "3"],
        [None, None, "2.1", "2"],
    ]
    boxes = [
        [(0, 0, 25, 10), (25, 0, 50, 10), (50, 0, 75, 10), (75, 0, 100, 10)],
        [(0, 10, 25, 50), (25, 10, 50, 30), (50, 10, 75, 20), (75, 10, 100, 20)],
        [None, None, (50, 20, 75, 30), (75, 20, 100, 30)],
        [None, (25, 30, 50, 50), (50, 30, 75, 40), (75, 30, 100, 40)],
        [None, None, (50, 40, 75, 50), (75, 40, 100, 50)],
    ]
    found = normalize(raw, 1, (0, 0, 100, 50), "native-lines", cell_boxes=boxes)
    assert found.rows == [
        ["WP-1", "Build", "1", "10"],
        ["WP-1", "Build", "1.1", "5"],
        ["WP-1", "QA", "2", "3"],
        ["WP-1", "QA", "2.1", "2"],
    ]
    inherited = found.cell_sources[1][0][0]
    assert inherited["text"] == "WP-1"
    assert inherited["bbox"] == [0, 10, 25, 50]
    assert inherited["role"] == "vertical_merge_expansion"
    assert any("Vertically merged group labels" in note for note in found.notes)


def test_vertical_expansion_requires_native_ruled_spanning_geometry():
    raw = [["Group", "Item", "Qty"], ["Alpha", "One", "1"], [None, "Two", "2"]]
    boxed_blank = [
        [(0, 0, 30, 10), (30, 0, 60, 10), (60, 0, 90, 10)],
        [(0, 10, 30, 20), (30, 10, 60, 20), (60, 10, 90, 20)],
        [(0, 20, 30, 30), (30, 20, 60, 30), (60, 20, 90, 30)],
    ]
    found = normalize(raw, 1, (0, 0, 90, 30), "native-lines", cell_boxes=boxed_blank)
    assert found.rows[1][0] == ""
    spanning = [
        boxed_blank[0],
        [(0, 10, 30, 30), (30, 10, 60, 20), (60, 10, 90, 20)],
        [None, (30, 20, 60, 30), (60, 20, 90, 30)],
    ]
    found = normalize(raw, 1, (0, 0, 90, 30), "native-text", cell_boxes=spanning)
    assert found.rows[1][0] == ""


def test_vertical_expansion_does_not_impute_numeric_cells():
    raw = [["Batch", "Item", "Qty"], ["12", "One", "1"], [None, "Two", "2"]]
    boxes = [
        [(0, 0, 30, 10), (30, 0, 60, 10), (60, 0, 90, 10)],
        [(0, 10, 30, 30), (30, 10, 60, 20), (60, 10, 90, 20)],
        [None, (30, 20, 60, 30), (60, 20, 90, 30)],
    ]
    found = normalize(raw, 1, (0, 0, 90, 30), "native-lines", cell_boxes=boxes)
    assert found.rows[1][0] == ""


def test_vertical_header_span_is_only_flattened_as_a_header():
    raw = [
        ["Code", "Movement", None],
        [None, "In", "Out"],
        ["A", "2", "1"],
        ["B", "3", "2"],
    ]
    boxes = [
        [(0, 0, 30, 20), (30, 0, 90, 10), None],
        [None, (30, 10, 60, 20), (60, 10, 90, 20)],
        [(0, 20, 30, 30), (30, 20, 60, 30), (60, 20, 90, 30)],
        [(0, 30, 30, 40), (30, 30, 60, 40), (60, 30, 90, 40)],
    ]
    found = normalize(raw, 1, (0, 0, 90, 40), "native-lines", cell_boxes=boxes)
    assert found.headers == ["Code", "Movement | In", "Movement | Out"]
    assert found.rows == [["A", "2", "1"], ["B", "3", "2"]]


def test_footer_removed():
    found = normalize(
        [["Code", "Amt"], ["A", "10"], ["Page 1 of 3", ""]],
        1,
        (0, 0, 100, 100),
        "native",
    )
    assert found.rows == [["A", "10"]]


def test_wrapped_cell_whitespace_normalized():
    found = normalize([["Code", "Amt"], ["A\nB", "10"]], 1, (0, 0, 100, 100), "native")
    assert found.rows[0][0] == "A B"


def test_word_grid_preserves_empty_middle_column():
    words = []
    for r, row in enumerate(
        [
            ["Code", "Units", "Value"],
            ["A", "2", "10"],
            ["B", "", "20"],
            ["C", "3", "30"],
        ]
    ):
        for c, text in enumerate(row):
            if text:
                words.append(
                    {
                        "x0": 10 + c * 80,
                        "x1": 30 + c * 80,
                        "top": 10 + r * 20,
                        "bottom": 20 + r * 20,
                        "text": text,
                    }
                )
    found = words_to_grid(words, 1, "native", 300, 300)
    assert found[0].rows[1] == ["B", "", "20"]


def test_stitch_does_not_mutate_inputs():
    a, b = t(), t(page=2)
    stitch([a, b])
    assert len(a.rows) == len(b.rows) == 1


def test_mixed_document_keeps_row_specific_engines():
    from truecell.validate import validate

    a = Table(
        ["Code", "Amt"],
        [["A", "12.00"], ["B", "13.00"]],
        1,
        (0, 0, 100, 100),
        "native-lines",
    )
    b = Table(["Code", "Amt"], [["C", "1O.00"]], 2, (0, 0, 100, 100), "ocr-tesseract", 0.7)
    joined, _ = stitch([a, b])
    assert joined[0].row_engines == ["native-lines", "native-lines", "ocr-tesseract"]
    assert any(i.code == "ocr_digit_risk" and i.page == 2 for i in validate(joined[0]))
