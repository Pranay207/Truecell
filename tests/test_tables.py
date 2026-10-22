"""Layout and stitching regressions protect row counts and provenance."""

import pytest
from openpyxl import load_workbook

from truecell.export import export_workbook
from truecell.models import Result, Table
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
    assert joined[0].join_receipt == {
        "page_joins": 1,
        "repeated_headers_removed": 1,
        "split_rows_recovered": 1,
        "pages": [1, 2],
        "rows_by_page": [{"page": 1, "rows": 1}, {"page": 2, "rows": 2}],
        "output_rows": 2,
    }


def test_split_row_does_not_duplicate_an_identical_spanning_label():
    first = t(rows=[["A", "Hardware", "", ""]])
    second = t(page=2, rows=[["", "Hardware", "3", "15"], ["B", "Next", "4", "20"]])

    joined, issues = stitch([first, second])

    assert joined[0].rows[0] == ["A", "Hardware", "3", "15"]
    assert any(issue.code == "split_row_join" for issue in issues)


def test_join_receipt_counts_headerless_continuation_without_claiming_header_removal():
    joined, _ = stitch(
        [
            t(rows=[["A", "First", "2", "10"]]),
            t(page=2, rows=[["B", "Second", "3", "15"]], detected=False),
            t(page=3, rows=[["C", "Third", "4", "20"]]),
        ]
    )

    assert joined[0].join_receipt == {
        "page_joins": 2,
        "repeated_headers_removed": 1,
        "split_rows_recovered": 0,
        "pages": [1, 2, 3],
        "rows_by_page": [
            {"page": 1, "rows": 1},
            {"page": 2, "rows": 1},
            {"page": 3, "rows": 1},
        ],
        "output_rows": 3,
    }


def test_single_page_table_has_a_zero_join_receipt():
    joined, _ = stitch([t(rows=[["A", "Only", "2", "10"]])])

    assert joined[0].join_receipt["pages"] == [1]
    assert joined[0].join_receipt["page_joins"] == 0
    assert joined[0].join_receipt["repeated_headers_removed"] == 0
    assert joined[0].join_receipt["split_rows_recovered"] == 0


def test_join_receipt_is_in_exported_workbook(tmp_path):
    joined, _ = stitch(
        [
            t(rows=[["A", "First", "2", "10"]]),
            t(page=2, rows=[["B", "Second", "3", "15"]]),
        ]
    )

    workbook = load_workbook(
        export_workbook(Result("joined.pdf", joined), tmp_path / "joined.xlsx")
    )
    receipt = workbook["Join Receipt"]
    assert receipt["A2"].value == "Data 1"
    assert receipt["B2"].value == "1, 2"
    assert receipt["C2"].value == 1
    assert receipt["D2"].value == 1
    assert receipt["E2"].value == 0
    assert [(receipt[f"F{row}"].value, receipt[f"G{row}"].value) for row in (2, 3)] == [
        (1, 1),
        (2, 1),
    ]


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


def test_merged_headers_do_not_consume_a_text_only_first_data_row():
    raw = [
        ["Identity", None, "Info", None],
        ["Code", "Name", "Category", "Status"],
        ["A", "Alpha", "Blue", "Open"],
        ["B", "Beta", "2", "3"],
        ["C", "Gamma", "4", "5"],
    ]

    found = normalize(raw, 1, (0, 0, 400, 100), "native")

    assert found.headers == [
        "Identity | Code",
        "Identity | Name",
        "Info | Category",
        "Info | Status",
    ]
    assert found.rows == raw[2:]


def test_merged_leaf_header_does_not_consume_the_next_text_data_row():
    raw = [
        ["Identity", None, "Info", None],
        ["Code", "Name", "Status", None],
        ["A", "Alpha", "Open", "Yes"],
        ["B", "Beta", "3", "4"],
        ["C", "Gamma", "5", "6"],
    ]
    boxes = [
        [(0, 0, 200, 20), None, (200, 0, 400, 20), None],
        [(0, 20, 100, 40), (100, 20, 200, 40), (200, 20, 400, 40), None],
        [(c * 100, 40, (c + 1) * 100, 60) for c in range(4)],
        [(c * 100, 60, (c + 1) * 100, 80) for c in range(4)],
        [(c * 100, 80, (c + 1) * 100, 100) for c in range(4)],
    ]

    found = normalize(raw, 1, (0, 0, 400, 100), "native-lines", cell_boxes=boxes)

    assert found.headers == [
        "Identity | Code",
        "Identity | Name",
        "Info | Status",
        "Info | Status",
    ]
    assert found.rows == raw[2:]


def test_headerless_ruled_leading_section_keeps_section_and_first_record():
    raw = [
        ["SECTION A", "", "", ""],
        ["A", "Alpha", "Open", "Yes"],
        ["B", "Beta", "3", "4"],
        ["C", "Gamma", "5", "6"],
    ]
    boxes = [[(c * 100, r * 20, (c + 1) * 100, (r + 1) * 20) for c in range(4)] for r in range(4)]

    found = normalize(raw, 1, (0, 0, 400, 80), "native-lines", cell_boxes=boxes)

    assert found.headers == ["Column 1", "Column 2", "Column 3", "Column 4"]
    assert found.rows == raw
    assert found.cell_sources[0][0][0]["role"] == "nested_group_label"


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
    found = normalize(raw, 1, (0, 0, 90, 30), "ocr-test-words", cell_boxes=spanning)
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


def test_three_axis_merged_headers_keep_source_backed_paths():
    raw = [
        ["Identity", None, "Operations", None, "Finance", None],
        [None, None, "Fulfillment", None, "Revenue", None],
        ["Code", "Name", "Planned", "Actual", "Gross", "Net"],
        ["A", "Alpha", "1", "2", "3", "4"],
        ["B", "Beta", "5", "6", "7", "8"],
    ]
    boxes = [
        [(0, 0, 200, 30), None, (200, 0, 400, 15), None, (400, 0, 600, 15), None],
        [None, None, (200, 15, 400, 30), None, (400, 15, 600, 30), None],
        [(c * 100, 30, (c + 1) * 100, 45) for c in range(6)],
        [(c * 100, 45, (c + 1) * 100, 60) for c in range(6)],
        [(c * 100, 60, (c + 1) * 100, 75) for c in range(6)],
    ]

    found = normalize(raw, 1, (0, 0, 600, 75), "native-lines", cell_boxes=boxes)

    assert found.headers == [
        "Identity | Code",
        "Identity | Name",
        "Operations | Fulfillment | Planned",
        "Operations | Fulfillment | Actual",
        "Finance | Revenue | Gross",
        "Finance | Revenue | Net",
    ]
    assert found.rows == raw[3:]
    assert [source["text"] for source in found.header_sources[3]] == [
        "Operations",
        "Fulfillment",
        "Actual",
    ]
    assert all(source["role"] == "merged_header_path" for source in found.header_sources[3])


def test_horizontal_body_merge_is_retained_without_filling_covered_columns():
    raw = [
        ["Code", "Description", "Qty", "Amount"],
        ["BUNDLE A", None, "3", "30"],
        ["A1", "First", "1", "10"],
        ["A2", "Second", "2", "20"],
    ]
    boxes = [
        [(0, 0, 100, 20), (100, 0, 200, 20), (200, 0, 300, 20), (300, 0, 400, 20)],
        [(0, 20, 200, 40), None, (200, 20, 300, 40), (300, 20, 400, 40)],
        [(0, 40, 100, 60), (100, 40, 200, 60), (200, 40, 300, 60), (300, 40, 400, 60)],
        [(0, 60, 100, 80), (100, 60, 200, 80), (200, 60, 300, 80), (300, 60, 400, 80)],
    ]

    found = normalize(raw, 1, (0, 0, 400, 80), "native-lines", cell_boxes=boxes)

    assert found.rows[0] == ["BUNDLE A", "", "3", "30"]
    assert found.cell_sources[0][0][0]["role"] == "horizontal_merge_label"
    assert found.cell_sources[0][1][0]["text"] == ""
    assert any("covered cells blank" in note for note in found.notes)


def test_unruled_vertical_group_gap_is_disclosed_without_imputation():
    raw = [["Group", "Item", "Qty"], ["Alpha", "One", "1"], [None, "Two", "2"]]
    boxes = [
        [(0, 0, 30, 10), (30, 0, 60, 10), (60, 0, 90, 10)],
        [(0, 10, 30, 20), (30, 10, 60, 20), (60, 10, 90, 20)],
        [None, (30, 20, 60, 30), (60, 20, 90, 30)],
    ]

    found = normalize(raw, 1, (0, 0, 90, 30), "native-text", cell_boxes=boxes)

    assert found.rows[1][0] == ""
    assert any("remain blank" in note for note in found.notes)


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
