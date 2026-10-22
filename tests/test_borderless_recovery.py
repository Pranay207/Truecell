"""General layout regressions discovered during external-document auditing."""

from truecell.layout import aligned_tables
from truecell.models import Table
from truecell.recover import candidate_key
from truecell.table import normalize, words_to_grid


def words(rows, y0=20, step=30, xs=(10, 130, 240)):
    output = []
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if value:
                output.append(
                    {
                        "x0": xs[c],
                        "x1": xs[c] + len(value) * 5,
                        "top": y0 + r * step,
                        "bottom": y0 + r * step + 10,
                        "text": value,
                    }
                )
    return output


def test_borderless_sparse_total_and_missing_amounts_retained():
    rows = [
        ["Code", "Qty", "Amt"],
        ["A", "2", "10"],
        ["B", "3", "15"],
        ["C", "4", "20"],
        ["D", "unknown", ""],
        ["E", "5", "25"],
        ["Total", "", "70"],
    ]
    tables = words_to_grid(words(rows), 1, "native-words", 500, 600)
    assert len(tables) == 1
    assert tables[0].rows == rows[1:]


def test_explicit_spanning_header_preserves_vertical_leaf_labels():
    table = normalize(
        [
            ["Code", "Units", "Movement", None],
            [None, None, "In", "Out"],
            ["A", "10", "3", "2"],
            ["B", "20", "5", "4"],
        ],
        1,
        (0, 0, 200, 100),
        "native-lines",
    )
    assert table.headers == ["Code", "Units", "Movement | In", "Movement | Out"]
    assert len(table.rows) == 2


def test_unruled_section_row_is_retained_as_hierarchy_not_attached_to_record():
    rows = [
        ["Code", "Description", "Qty", "Amount"],
        ["SECTION A", "", "", ""],
        ["A1", "First", "2", "10"],
        ["A2", "Second", "3", "15"],
        ["A3", "Third", "4", "20"],
    ]

    table = words_to_grid(words(rows, xs=(10, 130, 260, 370)), 1, "ocr-test", 500, 600)[0]

    assert table.rows[0] == ["SECTION A", "", "", ""]
    assert table.rows[1:] == rows[2:]
    assert table.cell_sources[0][0][0]["role"] == "nested_group_label"
    assert any("no child values were imputed" in note for note in table.notes)


def test_leading_section_does_not_hide_a_trailing_total():
    rows = [
        ["Code", "Description", "Qty", "Amount"],
        ["SECTION A", "", "", ""],
        ["A1", "First", "2", "10"],
        ["A2", "Second", "3", "15"],
        ["A3", "Third", "4", "20"],
        ["Total", "", "9", "45"],
    ]
    page_words = words(rows, xs=(10, 130, 260, 370))

    table = aligned_tables(page_words, 1, "ocr-test")[0]

    assert table.rows[0] == ["SECTION A", "", "", ""]
    assert table.rows[-1] == ["Total", "", "9", "45"]


def test_page_prose_cannot_outvote_trusted_native_grid():
    grid = Table(["Code", "Amt"], [["A", "12"], ["B", "13"]], 1, (0, 0, 100, 100), "native-lines")
    prose = Table(
        ["Column 1", "Column 2"],
        [["x" * 1000, "y" * 1000]] * 20,
        1,
        (0, 0, 500, 900),
        "native-words",
        header_detected=False,
    )
    assert candidate_key((10, [grid], None)) > candidate_key((50000, [prose], None))


def test_zero_is_not_cleaned_into_an_empty_cell():
    from truecell.table import clean

    assert clean(0) == "0"


def test_dense_upside_down_ocr_cannot_outvote_sparse_upright_totals():
    upright = Table(
        ["Ref", "Description", "Units", "Amount"],
        [
            ["1", "Paper", "2", "10"],
            ["2", "Ink", "3", "15"],
            ["", "Sub Total", "", "25"],
            ["", "Tax", "", "5"],
            ["", "Grand Total", "", "30"],
        ],
        1,
        (0, 0, 400, 300),
        "ocr-test",
        0.97,
    )
    nonsense = Table(
        ["0S'2I", "uondiosag", "0l", "00'6I"],
        [["0S'2I", "uondiosag", "0l", "00'6I"]] * 5,
        1,
        (0, 0, 400, 300),
        "ocr-test",
        0.75,
    )
    assert candidate_key((100, [upright], None)) > candidate_key((500, [nonsense], None))


def test_negative_rotated_candidate_cannot_outvote_credible_ocr_grid():
    credible = Table(
        ["Invoice", "Date", "Client", "Amount"],
        [["INV-0001", "2026-10-01", "Client 1", "12.00"]],
        1,
        (0, 0, 400, 300),
        "ocr-tesseract-words",
        0.9,
    )
    rotated = Table(
        ["pled", "yinog", "00'S", "00�9"],
        [["pled", "yinog", "00�S", "088"]] * 5,
        1,
        (0, 0, 400, 300),
        "ocr-tesseract-words",
        0.9,
    )

    assert candidate_key((663, [credible], None)) > candidate_key((-164, [rotated], None))
