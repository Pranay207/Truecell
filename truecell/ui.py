"""Local review workspace. Document content is never interpolated into HTML."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import ImageDraw

from .assurance import challenge
from .constraints import coverage
from .export import export_workbook
from .models import Result
from .ocr import available_engines
from .pipeline import convert
from .review import apply_edit, complete_review, digest, fingerprint, review_current
from .router import open_document, render_page
from .workspace import (
    create_job,
    job_path,
    list_jobs,
    load_result,
    save_result,
    set_status,
)

PROJECT = Path(__file__).resolve().parents[1]


def _export(saved: dict) -> bytes:
    key = digest({"data": fingerprint(saved["result"]), "review": saved["result"].review})
    if saved.get("export_key") != key:
        with tempfile.TemporaryDirectory(prefix="truecell-export-") as temporary:
            path = export_workbook(saved["result"], Path(temporary) / "result.xlsx")
            saved["xlsx"] = path.read_bytes()
        saved["export_key"] = key
    return saved["xlsx"]


def _replace(saved: dict, result: Result) -> None:
    if saved.get("job_id"):
        save_result(saved["job_id"], result)
    saved["result"] = result
    _export(saved)


def _run(filename: str, content: bytes, verify: bool, force: bool = False) -> None:
    identifier, source = create_job(filename, content)
    st.session_state["active_job"] = identifier
    _process(identifier, source, filename, verify, force)


def _process(
    identifier: str, source: Path, filename: str, verify: bool, force: bool = False
) -> None:
    bar = st.progress(0, text="Inspecting the document…")
    set_status(identifier, "processing", options={"verify": verify, "force": force})
    try:
        result = convert(
            source,
            verify=verify,
            force_ocr=force,
            checkpoint_dir=job_path(identifier) / "pages",
            progress=lambda p, n: bar.progress(p / n, text=f"Processed page {p} of {n}"),
        )
        result.source = filename
        save_result(identifier, result)
        saved = {
            "result": result,
            "name": Path(filename).stem + ".xlsx",
            "job_id": identifier,
            "source": str(source),
        }
        _export(saved)
        st.session_state["conversion"] = saved
        st.session_state.pop("lab_result", None)
    except Exception as exc:
        set_status(identifier, "failed", error=str(exc))
        st.error(f"Processing stopped: {exc}. Completed page checkpoints are retained for resume.")
    finally:
        bar.empty()


def _load(identifier: str) -> None:
    result = load_result(identifier)
    metadata = next(r for r in list_jobs() if r["id"] == identifier)
    source = job_path(identifier) / metadata["source"]
    st.session_state["conversion"] = {
        "result": result,
        "name": Path(metadata["name"]).stem + ".xlsx",
        "job_id": identifier,
        "source": str(source),
    }
    st.session_state["active_job"] = identifier


def _source_preview(saved: dict, records: list[dict], full_page: bool = False) -> None:
    if not saved.get("source"):
        st.info("Reopen a saved document to view the original source.")
        return
    record = next((r for r in records if r.get("bbox")), records[0] if records else None)
    if not record:
        st.warning("No source box was recovered for this cell. Compare the source page manually.")
        return
    page_number = record["page"]
    with open_document(saved["source"]) as document:
        page = document[page_number - 1]
        image = render_page(page, 130)
        box = record.get("bbox")
        if box:
            sx, sy = image.width / page.rect.width, image.height / page.rect.height
            x0, y0, x1, y1 = [box[i] * (sx if i % 2 == 0 else sy) for i in range(4)]
            x0, x1 = max(0, x0), min(image.width, x1)
            y0, y1 = max(0, y0), min(image.height, y1)
            ImageDraw.Draw(image).rectangle((x0, y0, x1, y1), outline="#e65e42", width=3)
            if not full_page:
                px, py = max(70, (x1 - x0) * 0.5), max(55, (y1 - y0) * 1.4)
                image = image.crop(
                    (
                        max(0, int(x0 - px)),
                        max(0, int(y0 - py)),
                        min(image.width, int(x1 + px)),
                        min(image.height, int(y1 + py)),
                    )
                )
        st.image(
            image,
            caption=f"Original source · page {page_number} · selected cell outlined",
            use_container_width=True,
        )
    if len({r["page"] for r in records}) > 1:
        st.caption("This record spans multiple pages; all source parts are listed below.")


def _table_frame(table) -> pd.DataFrame:
    frame = pd.DataFrame(table.rows)
    frame.columns = [
        f"{i + 1}. {table.headers[i] if i < len(table.headers) else 'Extra column'}"
        for i in range(len(frame.columns))
    ]
    frame.index = range(1, len(frame) + 1)
    return frame


def _inspector(saved: dict, table_index: int) -> None:
    result = saved["result"]
    table = result.tables[table_index]
    if not table.rows:
        return
    selectors = st.columns([1, 2])
    row = (
        selectors[0].number_input(
            "Data row",
            min_value=1,
            max_value=len(table.rows),
            value=1,
            key=f"row_{table_index}",
        )
        - 1
    )
    header = st.checkbox("Inspect or correct the header", key=f"header_{table_index}")
    if header:
        row = -1
    column = selectors[1].selectbox(
        "Column",
        range(len(table.headers) if header else len(table.rows[row])),
        format_func=lambda c: f"{c + 1}. {table.headers[c] if c < len(table.headers) else 'Extra column'}",
        key=f"col_{table_index}",
    )
    value = table.headers[column] if header else table.rows[row][column]
    records = table.header_sources[column] if header else table.cell_sources[row][column]
    st.caption("CURRENT VALUE")
    st.code(value or "(empty)", language=None)
    _source_preview(saved, records, st.checkbox("Show full source page", key=f"full_{table_index}"))
    if records:
        with st.expander("Readings and source coordinates"):
            st.dataframe(
                [
                    {
                        "page": s["page"],
                        "reading": s.get("text", ""),
                        "engine": s.get("engine", ""),
                        "OCR score": s.get("confidence"),
                        "source box": str(s.get("bbox")),
                        "role": s.get("role", "extracted"),
                    }
                    for s in records
                ],
                hide_index=True,
                use_container_width=True,
            )
    with st.expander("Correct this cell after checking the source"):
        with st.form(f"edit_{table_index}_{row}_{column}"):
            new = st.text_input("Reviewed value", value=value)
            note = st.text_area("Reason for change")
            submitted = st.form_submit_button("Save correction")
        if submitted:
            try:
                _replace(saved, apply_edit(result, table_index, row, column, new, note))
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def _equations(saved: dict, table_index: int) -> None:
    result = saved["result"]
    relations = [r for r in result.constraints if r["table"] == table_index + 1]
    st.subheader("What the numbers say")
    st.write(
        "Relations are inferred from repeated patterns in this document. Matching a relation is evidence to inspect, not proof that a value is correct."
    )
    if not relations:
        st.info("Not enough repeated numeric evidence to infer an equation in this table.")
    for relation in relations:
        with st.container(border=True):
            st.text(relation["formula"])
            st.caption(
                f"{relation['matched']} of {relation['checked']} eligible rows agree · {len(relation['violations'])} discrepancies"
            )
            if relation["violations"]:
                st.dataframe(
                    [
                        {
                            "data row": v["row"] + 1,
                            "column": v["column"] + 1,
                            "observed": v["observed"],
                            "equation expects": v["expected"],
                        }
                        for v in relation["violations"]
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
    st.subheader("Repair proposals")
    single = st.checkbox("Include suggestions supported by only one equation")
    proposals = [
        p
        for p in result.proposals
        if p["table"] == table_index + 1 and (single or p["support_count"] >= 2)
    ]
    if not proposals:
        st.caption("No proposals with this evidence threshold. Original values remain unchanged.")
        return
    proposal = st.selectbox(
        "Inspect a proposal",
        proposals,
        format_func=lambda p: f"Row {p['row'] + 1}, column {p['column'] + 1}: {p['observed']} → {p['proposed']} ({p['support_count']} equations)",
    )
    st.warning(
        "A mathematically consistent replacement can still be wrong. The source itself may contain an error. Nothing is applied automatically."
    )
    _source_preview(
        saved,
        result.tables[table_index].cell_sources[proposal["row"]][proposal["column"]],
    )
    with st.expander("Supporting equation receipts", expanded=True):
        for equation in proposal["supporting_equations"]:
            st.code(equation, language=None)
    if st.button("Preview the effect without saving"):
        preview = apply_edit(
            result,
            table_index,
            proposal["row"],
            proposal["column"],
            proposal["proposed"],
            "Counterfactual preview only",
        )
        before = sum(len(r["violations"]) for r in result.constraints)
        after = sum(len(r["violations"]) for r in preview.constraints)
        st.info(
            f"The proposed change would move failed equation checks from {before} to {after}. The working data has not changed."
        )
    with st.form("apply_proposal"):
        checked = st.checkbox(
            "I inspected the source and understand this may change a source error."
        )
        note = st.text_input("Correction reason")
        submitted = st.form_submit_button("Apply to working copy")
    if submitted:
        if not checked:
            st.error("Inspect the source before applying a proposal.")
        else:
            try:
                _replace(
                    saved,
                    apply_edit(
                        result,
                        table_index,
                        proposal["row"],
                        proposal["column"],
                        proposal["proposed"],
                        note,
                    ),
                )
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def _lab(saved: dict, table_index: int) -> None:
    st.subheader("Challenge the validator")
    st.write(
        "Hide the column names, perturb sampled numeric values in disposable copies, and run the actual validator. Misses stay visible. This measures validation sensitivity on this extraction; it does not measure OCR accuracy."
    )
    st.caption(
        "Up to 24 deterministic test edits. For large tables, the first 120 data rows are used."
    )
    if st.button("Run controlled error injections"):
        from copy import deepcopy

        table = deepcopy(saved["result"].tables[table_index])
        table.rows = table.rows[:120]
        table.provenance = table.provenance[:120]
        table.cell_sources = table.cell_sources[:120]
        table.row_engines = table.row_engines[:120]
        with st.spinner("Running the production validator against each test edit…"):
            st.session_state["lab_result"] = {
                "table": table_index,
                "snapshot": fingerprint(saved["result"]),
                "report": challenge(table, 24),
            }
    record = st.session_state.get("lab_result")
    if (
        record
        and record["snapshot"] == fingerprint(saved["result"])
        and record["table"] == table_index
    ):
        report = record["report"]
        st.metric(
            "Test edits that triggered a new finding",
            f"{report['caught']} / {report['tested']}",
        )
        st.caption(
            "Columns without inferred equations: "
            + (", ".join(map(str, report["unmodeled_columns"])) or "none")
        )
        st.dataframe(report["cases"], hide_index=True, use_container_width=True)
        st.download_button(
            "Download challenge results",
            json.dumps(report, indent=2),
            file_name="validation-challenges.json",
            mime="application/json",
        )


def _review_export(saved: dict) -> None:
    result = saved["result"]
    reviewed = review_current(result)
    st.subheader("Review this exact snapshot")
    if reviewed:
        st.success("This snapshot has a recorded human source-check attestation.")
    else:
        st.info(
            "Unreviewed extraction. Exports retain this status until a source check is recorded."
        )
    st.caption(
        "Any correction invalidates the previous review. Hashes detect changed snapshots; they do not establish reviewer identity or guarantee accuracy."
    )
    with st.form("complete_review"):
        checked = st.checkbox(
            "I checked the original source pages and reviewed the outstanding findings."
        )
        note = st.text_area("Review note and accepted findings")
        submitted = st.form_submit_button("Record review for this snapshot")
    if submitted:
        try:
            _replace(saved, complete_review(result, checked, note))
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    left, right = st.columns(2)
    left.download_button(
        "Download Excel with evidence",
        _export(saved),
        file_name=saved["name"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    right.download_button(
        "Download full audit JSON",
        json.dumps(result.to_dict(), indent=2),
        file_name="truecell-audit.json",
        mime="application/json",
    )
    with st.expander("Source and snapshot fingerprints"):
        st.write("Source SHA-256")
        st.code(result.source_sha256, language=None)
        st.write("Current snapshot SHA-256")
        st.code(fingerprint(result), language=None)
    if result.history:
        st.subheader("Correction history")
        st.dataframe(
            [
                {k: v for k, v in e.items() if k not in {"previous", "sha256"}}
                for e in result.history
            ],
            hide_index=True,
            use_container_width=True,
        )
    if saved.get("job_id"):
        baseline = load_result(saved["job_id"], baseline=True)
        st.download_button(
            "Download immutable original extraction",
            json.dumps(baseline.to_dict(), indent=2),
            file_name="original-extraction.json",
            mime="application/json",
        )


def main() -> None:
    """Render the local source review and verification workspace."""
    st.set_page_config(page_title="Truecell Studio", page_icon="📑", layout="wide")
    st.markdown(
        """<style>
    .stApp {background:#f5f7fa;color:#152b40}
    .block-container {max-width:1640px;padding-top:2rem}
    h1,h2,h3 {letter-spacing:-.025em}
    [data-testid="stSidebar"] {background:#edf2f6;border-right:1px solid #d4dfe8}
    [data-testid="stMetric"] {background:white;border:1px solid #d4dfe8;padding:1rem;border-radius:10px}
    .eyebrow {color:#087d78;font-size:.8rem;letter-spacing:.15em;font-weight:700}
    </style>""",
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.markdown("### TRUECELL STUDIO")
        st.caption("Local extraction · source evidence · numeric verification")
        jobs = list_jobs()
        if jobs:
            selected = st.selectbox(
                "Saved documents",
                jobs,
                format_func=lambda j: f"{j['name']} · {j['status']}",
            )
            if st.button("Open saved workspace"):
                try:
                    _load(selected["id"])
                    st.rerun()
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
            if selected["status"] != "complete" and st.button("Resume completed page checkpoints"):
                options = selected.get("options", {})
                _process(
                    selected["id"],
                    job_path(selected["id"]) / selected["source"],
                    selected["name"],
                    options.get("verify", False),
                    options.get("force", False),
                )
        st.divider()
        st.caption("Available OCR: " + (", ".join(available_engines()) or "none"))
        st.caption(
            "Documents and review history stay in the local workspace. Use only public or dummy files for the challenge."
        )
    st.markdown(
        '<p class="eyebrow">DOCUMENT INTELLIGENCE / SOURCE REVIEW</p>',
        unsafe_allow_html=True,
    )
    st.title("Document to Excel, with evidence.")
    st.write(
        "Extract tables, inspect the original cells, and check the arithmetic behind the numbers."
    )
    with st.expander("Open a document", expanded="conversion" not in st.session_state):
        upload = st.file_uploader(
            "PDF or scanned document · up to 50 pages",
            type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"],
        )
        controls = st.columns([2, 2, 1])
        verify = controls[0].checkbox(
            "Independent OCR check of native pages",
            help="Adds a separate reading and reports disagreements. This takes longer.",
        )
        force = controls[1].checkbox("Force OCR", help="Use when a PDF has a damaged text layer.")
        if controls[2].button("Extract tables", type="primary", disabled=upload is None):
            _run(upload.name, upload.getvalue(), verify, force)
        st.caption("Try a public dummy document")
        examples = st.columns(3)
        for container, label, name in zip(
            examples,
            ["Invoice register", "Find a wrong balance", "Skewed scan"],
            ["A_invoice_register.pdf", "B_bank_errors.pdf", "D_skew_5deg.pdf"],
        ):
            if container.button(label, use_container_width=True):
                path = PROJECT / "samples" / name
                _run(name, path.read_bytes(), False)
    if "conversion" not in st.session_state:
        return
    saved = st.session_state["conversion"]
    result = saved["result"]
    columns = st.columns(4)
    for container, label, value in zip(
        columns,
        ["Pages", "Tables", "Data rows", "Review findings"],
        [
            len(result.pages),
            len(result.tables),
            sum(len(t.rows) for t in result.tables),
            len(result.issues),
        ],
    ):
        container.metric(label, value)
    counts = coverage(result)
    st.caption(
        f"{result.source} · {result.seconds:.1f}s · {counts['cells_with_source_boxes']} / {counts['cells']} data cells have source boxes · {counts['equation_checks']} equation checks · {'Reviewed snapshot' if review_current(result) else 'Unreviewed'}"
    )
    if not result.tables:
        st.warning("No tables recovered. Inspect the page audit before using this result.")
        st.dataframe([asdict(i) for i in result.issues], use_container_width=True)
        return
    table_index = st.selectbox(
        "Table",
        range(len(result.tables)),
        format_func=lambda i: f"Table {i + 1} · {len(result.tables[i].rows)} rows · {len(result.tables[i].headers)} columns",
    )
    data, equations, lab, review, audit = st.tabs(
        [
            "Table & source",
            "Equation receipts",
            "Challenge lab",
            "Review & export",
            "Engine audit",
        ]
    )
    with data:
        left, right = st.columns([1.4, 1], gap="large")
        with left:
            st.subheader("Extracted values")
            st.dataframe(
                _table_frame(result.tables[table_index]),
                use_container_width=True,
                height=430,
            )
            if result.issues:
                st.subheader("Findings to review")
                st.dataframe(
                    [
                        {
                            "severity": i.severity,
                            "page": i.page,
                            "source row": i.row,
                            "column": i.column,
                            "reason": i.reason,
                        }
                        for i in result.issues
                        if i.table in (None, table_index + 1)
                    ],
                    hide_index=True,
                    use_container_width=True,
                    height=230,
                )
        with right:
            st.subheader("Inspect a source cell")
            _inspector(saved, table_index)
    with equations:
        _equations(saved, table_index)
    with lab:
        _lab(saved, table_index)
    with review:
        _review_export(saved)
    with audit:
        st.subheader("Every attempt stays visible")
        st.dataframe(
            [
                {
                    "page": p.page,
                    "route": p.route,
                    "strategy": a.strategy,
                    "engine": a.engine,
                    "selected": a.selected,
                    "tables": a.tables,
                    "cells": a.cells,
                    "seconds": round(a.seconds, 3),
                    "error": a.error,
                }
                for p in result.pages
                for a in p.attempts
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "OCR recognition scores and inferred-equation agreement are not measured extraction accuracy."
        )
