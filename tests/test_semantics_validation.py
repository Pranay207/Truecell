"""Regression coverage for semantic roles and evidence-led continuity checks."""

from truecell.anchors import header_tables
from truecell.constraints import discover
from truecell.models import Table
from truecell.semantics import infer_column_semantics
from truecell.stitch import stitch
from truecell.table import normalize
from truecell.validate import validate
from truecell.values import kind, number


def _table(headers, rows, *, provenance=None):
    return Table(
        headers,
        rows,
        1,
        (0, 0, 400, 300),
        "native-lines",
        provenance=provenance or [],
    )


def _line(values, y, *, bold=False):
    return [
        {
            "text": value,
            "x0": 20 + 110 * c,
            "x1": 20 + 110 * c + len(value) * 4,
            "top": y,
            "bottom": y + 10,
            "fontname": "Helvetica-Bold" if bold else "Helvetica",
        }
        for c, value in enumerate(values)
        if value
    ]


def test_full_width_document_title_is_not_flattened_into_headers():
    raw = [
        ["POLICE STAFF LIST", None, None, None],
        ["S No", "Officer Name", "Phone", "Balance"],
        ["1", "Asha Rao", "+91 98765 43210", "100.00"],
        ["2", "Bina Das", "+91 98765 43211", "120.00"],
    ]
    boxes = [
        [(0, 0, 400, 20), None, None, None],
        [(0, 20, 70, 40), (70, 20, 220, 40), (220, 20, 320, 40), (320, 20, 400, 40)],
        [(0, 40, 70, 60), (70, 40, 220, 60), (220, 40, 320, 60), (320, 40, 400, 60)],
        [(0, 60, 70, 80), (70, 60, 220, 80), (220, 60, 320, 80), (320, 60, 400, 80)],
    ]

    table = normalize(raw, 1, (0, 0, 400, 80), "native-lines", cell_boxes=boxes)

    assert table.headers == ["S No", "Officer Name", "Phone", "Balance"]
    assert table.rows[0][1] == "Asha Rao"
    assert table.page_summaries == [
        {
            "page": 1,
            "text": "POLICE STAFF LIST",
            "bbox": [0, 0, 400, 20],
            "role": "document_title",
        }
    ]


def test_title_allows_a_text_only_leaf_header_without_promoting_the_title():
    table = normalize(
        [
            ["EMPLOYEE DIRECTORY", None, None],
            ["Name", "Department", "City"],
            ["Asha Rao", "Finance", "Hyderabad"],
            ["Bina Das", "Legal", "Kolkata"],
        ],
        1,
        (0, 0, 300, 100),
        "native-lines",
    )

    assert table.headers == ["Name", "Department", "City"]
    assert table.rows == [
        ["Asha Rao", "Finance", "Hyderabad"],
        ["Bina Das", "Legal", "Kolkata"],
    ]


def test_long_full_width_numbered_section_caption_is_not_a_parent_header():
    raw = [
        ["Regional training attendance - section 10", None, None, None],
        ["Batch", "Date", "Participant Name", "Score"],
        ["BT-0001", "2026-04-02", "Anita Rao", "84"],
        ["BT-0002", "2026-04-03", "Bina Das", "91"],
    ]
    boxes = [
        [(0, 0, 400, 20), None, None, None],
        [(0, 20, 100, 40), (100, 20, 200, 40), (200, 20, 300, 40), (300, 20, 400, 40)],
        [(0, 40, 100, 60), (100, 40, 200, 60), (200, 40, 300, 60), (300, 40, 400, 60)],
        [(0, 60, 100, 80), (100, 60, 200, 80), (200, 60, 300, 80), (300, 60, 400, 80)],
    ]

    table = normalize(raw, 10, (0, 0, 400, 80), "native-lines", cell_boxes=boxes)

    assert table.headers == ["Batch", "Date", "Participant Name", "Score"]
    assert table.page_summaries[0]["text"] == "Regional training attendance - section 10"


def test_two_text_fields_on_one_continuation_line_join_with_source_evidence():
    words = (
        _line(["ID", "Name", "Address", "Qty", "Rate", "Amount"], 20, bold=True)
        + _line(["A1", "Anita", "Road One", "2", "5", "10"], 45)
        + _line(["", "Kumar", "Hyderabad", "", "", ""], 58)
        + _line(["A2", "Bina", "Road Two", "3", "5", "15"], 85)
        + _line(["A3", "Chitra", "Road Three", "4", "5", "20"], 115)
    )

    table = header_tables(words, 1)[0]

    assert table.rows[0][:3] == ["A1", "Anita Kumar", "Road One Hyderabad"]
    assert table.cell_sources[0][1][0]["role"] == "wrapped_continuation_join"
    assert "continuation lines joined" in table.notes[-1]


def test_full_width_nested_group_row_is_retained_and_labelled_without_imputation():
    raw = [
        ["Code", "Description", "Qty", "Amount"],
        ["SECTION A", None, None, None],
        ["A1", "First", "2", "10"],
        ["A2", "Second", "3", "15"],
    ]
    boxes = [
        [(0, 0, 50, 20), (50, 0, 220, 20), (220, 0, 300, 20), (300, 0, 400, 20)],
        [(0, 20, 400, 40), None, None, None],
        [(0, 40, 50, 60), (50, 40, 220, 60), (220, 40, 300, 60), (300, 40, 400, 60)],
        [(0, 60, 50, 80), (50, 60, 220, 80), (220, 60, 300, 80), (300, 60, 400, 80)],
    ]

    table = normalize(raw, 1, (0, 0, 400, 80), "native-lines", cell_boxes=boxes)

    assert table.rows[0] == ["SECTION A", "", "", ""]
    assert table.cell_sources[0][0][0]["role"] == "nested_group_label"
    assert table.rows[1] == ["A1", "First", "2", "10"]


def test_repeated_page_headers_repair_a_damaged_first_reading_with_evidence():
    first = _table(
        ["S No", "Ofcr Nm", "Phone", "Balance"],
        [["1", "Asha", "+91 98765 43210", "10"]],
    )
    second = Table(
        ["S No", "Officer Name", "Phone", "Balance"],
        [["2", "Bina", "+91 98765 43211", "20"]],
        2,
        (0, 0, 400, 300),
        "native-lines",
    )
    third = Table(
        ["S No", "Officer Name", "Phone", "Balance"],
        [["3", "Chitra", "+91 98765 43212", "30"]],
        3,
        (0, 0, 400, 300),
        "native-lines",
    )
    for table in (first, second, third):
        table.header_sources = [
            [{"page": table.page, "bbox": [c * 100, 0, (c + 1) * 100, 20], "text": value}]
            for c, value in enumerate(table.headers)
        ]

    joined, issues = stitch([first, second, third])

    assert joined[0].headers[1] == "Officer Name"
    assert joined[0].join_receipt["header_repairs"] == 1
    assert any(issue.code == "header_consensus_repair" and issue.column == 2 for issue in issues)
    repair = next(
        source
        for source in joined[0].header_sources[1]
        if source.get("role") == "header_consensus_repair"
    )
    assert repair["initial_reading"] == "Ofcr Nm"
    assert repair["supporting_pages"] == [2, 3]


def test_semantic_roles_use_headers_and_data_without_rewriting_values():
    table = _table(
        ["Employee ID", "Date", "Mobile Number", "Qty", "Amount", "Closing Balance"],
        [
            ["EMP-001", "2026-10-01", "+91 98765 43210", "2", "₹10.00", "100.00"],
            ["EMP-002", "2026-10-02", "+91 98765 43211", "3", "₹15.00", "115.00"],
            ["EMP-003", "2026-10-03", "+91 98765 43212", "4", "₹20.00", "135.00"],
        ],
    )
    original = [row[:] for row in table.rows]

    roles = [column.role for column in infer_column_semantics(table)]

    assert roles == ["id", "date", "phone", "quantity", "amount", "balance"]
    assert table.rows == original


def test_unicode_currency_and_additional_unambiguous_dates_are_typed():
    assert str(number("₹1,250.50")) == "1250.50"
    assert kind("₹1,250.50") == "currency"
    assert kind("2026/10/21") == "date"


def test_hindi_and_telugu_headers_provide_semantic_signals():
    hindi = _table(
        ["आईडी", "तारीख", "मोबाइल", "राशि"],
        [["001", "2026-10-21", "98765 43210", "₹10"]],
    )
    telugu = _table(
        ["ఐడి", "తేదీ", "మొబైల్", "మొత్తం"],
        [["001", "2026-10-21", "98765 43210", "₹10"]],
    )

    assert [value.role for value in infer_column_semantics(hindi)] == [
        "id",
        "date",
        "phone",
        "amount",
    ]
    assert [value.role for value in infer_column_semantics(telugu)] == [
        "id",
        "date",
        "phone",
        "total",
    ]


def test_singular_unit_requires_numeric_support_but_qty_remains_strong():
    organisational = _table(
        ["Unit", "Name"],
        [[f"Unit {index}", f"Officer {index}"] for index in range(1, 19)],
    )
    numeric = _table(["Unit", "Name"], [[str(index), f"Item {index}"] for index in range(1, 6)])
    explicit = _table(["Qty", "Name"], [["unknown", "Item"]])

    assert infer_column_semantics(organisational)[0].role == "text"
    assert not any(
        issue.code == "semantic_type_mismatch" and issue.column == 1
        for issue in validate(organisational)
    )
    assert infer_column_semantics(numeric)[0].role == "quantity"
    assert infer_column_semantics(explicit)[0].role == "quantity"
    assert any(issue.code == "semantic_type_mismatch" for issue in validate(explicit))


def test_stitched_document_titles_emit_one_finding_on_their_actual_page():
    fragments = []
    for page, title in enumerate(
        ["NORTH REGION STAFF LIST", "SOUTH REGION STAFF LIST", "WEST REGION STAFF LIST"],
        1,
    ):
        fragment = normalize(
            [
                [title, None, None],
                ["ID", "Name", "Amount"],
                [str(page), f"Officer {page}", str(page * 10)],
            ],
            page,
            (0, 0, 300, 100),
            "native-lines",
        )
        fragments.append(fragment)
    fragments[1].page_summaries.append(dict(fragments[1].page_summaries[0]))

    joined, _issues = stitch(fragments)
    title_findings = [
        issue
        for issue in validate(joined[0])
        if issue.code == "layout_review" and issue.reason.startswith("Full-width document title")
    ]

    assert len(title_findings) == 3
    assert [issue.page for issue in title_findings] == [1, 2, 3]


def test_required_high_risk_shift_sequence_and_count_checks_are_explicit():
    rows = [
        ["001", "2026-10-01", "+91 98765 43210", "10.00"],
        ["002", "2026-10-02", "+91 98765 43211", "20.00"],
        ["003", "2026-10-03", "unknown", "30.00"],
        ["004", "2026-10-04", "+91 98765 43213", "40.00"],
        ["006", "2026-10-05", "", "50.00"],
        ["", "007", "2026-10-06", "+91 98765 43215"],
        ["008", "2026-10-07", "+91 98765 43216", "70.00"],
        ["009", "2026-10-08", "+91 98765 43217", "80.00"],
        ["010", "2026-10-09", "+91 98765 43218", "90.00"],
    ]
    provenance = [[(1, i + 1)] for i in range(4)] + [[(2, i + 1)] for i in range(5)]
    table = _table(["Record ID", "Date", "Phone", "Amount"], rows, provenance=provenance)
    table.page_summaries = [{"page": 2, "text": "Total records: 10", "bbox": [0, 280, 100, 295]}]

    findings = validate(table)
    codes = {finding.code for finding in findings}

    assert "semantic_type_mismatch" in codes
    assert "required_value_missing" in codes
    assert "shifted_columns" in codes
    assert "cross_page_sequence_gap" in codes
    assert "record_count_mismatch" in codes
    assert table.rows == rows


def test_identifier_column_is_not_used_to_invent_arithmetic_relations():
    table = _table(
        ["Record ID", "Quantity", "Unit Price", "Amount"],
        [[str(i), str(i + 1), str(i + 2), str((i + 1) * (i + 2))] for i in range(1, 9)],
    )

    relations = discover(table)

    assert all(0 not in relation["columns"] for relation in relations)


def test_identifier_column_is_excluded_from_validation_equation_discovery():
    table = _table(
        ["Record ID", "Measure A", "Measure B"],
        [[str(i), str(i + 10), str(2 * i + 10)] for i in range(1, 9)],
    )

    assert not any(issue.code == "row_arithmetic" for issue in validate(table))


def test_join_receipt_page_gap_is_never_silently_accepted():
    table = _table(["Record ID", "Name"], [["001", "Asha"], ["002", "Bina"]])
    table.join_receipt = {
        "pages": [1, 3],
        "page_joins": 1,
        "rows_by_page": [{"page": 1, "rows": 2}],
    }

    codes = {issue.code for issue in validate(table)}

    assert "page_continuity_gap" in codes
