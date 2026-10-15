"""Small local upload, progress, review and Excel download interface."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import tempfile

import streamlit as st
import pandas as pd

from truecell.pipeline import convert
from truecell.ocr import available_engines

st.set_page_config(page_title="Truecell | Document to Excel", page_icon="📑", layout="wide")
st.markdown("""<style>
.stApp {background:#f6f8fb;color:#18324b}
.block-container {max-width:1200px;padding-top:2.5rem}
h1,h2,h3 {letter-spacing:-.03em}
[data-testid="stMetric"] {background:white;border:1px solid #dce4ed;padding:1rem;border-radius:12px}
.eyebrow {color:#137f79;font-size:.8rem;letter-spacing:.16em;font-weight:700}
</style>""", unsafe_allow_html=True)
st.markdown('<p class="eyebrow">TRUECELL / DOCUMENT INTELLIGENCE</p>', unsafe_allow_html=True)
st.title("From document to structured Excel.")
st.write("Extract tables, join pages, and review uncertain values in one workbook.")
with st.sidebar:
    st.subheader("Processing")
    st.write("Local CPU extraction · up to 50 pages")
    st.caption("OCR engines: " + (", ".join(available_engines()) or "none installed"))
    recovery = st.toggle("Retry uncertain pages", value=True)
    st.caption("Yellow cells in Excel link to findings in the Validation Report. Original values are retained.")
    st.divider()
    st.caption("Use public or dummy documents for the challenge.")

upload = st.file_uploader("Choose a PDF or scanned document", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"])
if st.button("Convert to Excel", type="primary", disabled=upload is None):
    st.session_state.pop("conversion", None)
    bar = st.progress(0, text="Opening document…")
    try:
        with tempfile.TemporaryDirectory(prefix="truecell-") as temporary:
            source = Path(temporary) / Path(upload.name).name
            output = Path(temporary) / "converted.xlsx"
            source.write_bytes(upload.getvalue())
            result = convert(source, output, recover=recovery,
                             progress=lambda p, n: bar.progress(p/n, text=f"Processed page {p} of {n}"))
            result.source = upload.name
            st.session_state.conversion = {
                "result": result, "xlsx": output.read_bytes(),
                "name": Path(upload.name).stem + ".xlsx"}
        bar.empty()
    except Exception as exc:
        bar.empty()
        st.error(str(exc))

if "conversion" in st.session_state:
    saved = st.session_state.conversion
    result = saved["result"]
    cols = st.columns(4)
    cols[0].metric("Pages processed", len(result.pages))
    cols[1].metric("Tables", len(result.tables))
    cols[2].metric("Data rows", sum(len(t.rows) for t in result.tables))
    cols[3].metric("Review findings", len(result.issues))
    st.caption(f"Processed in {result.seconds:.1f}s. Findings are checks to review, not a measured error rate.")
    download, audit = st.columns([1, 1])
    download.download_button("Download Excel workbook", data=saved["xlsx"], file_name=saved["name"],
                             mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    audit.download_button("Download audit JSON", json.dumps(result.to_dict(), indent=2),
                          file_name="truecell-audit.json", mime="application/json")
    data_tab, validation_tab, pages_tab = st.tabs(["Extracted tables", "Validation findings", "Page audit"])
    with data_tab:
        if not result.tables:
            st.warning("No tables recovered. Check the page audit for details.")
        for i, table in enumerate(result.tables, 1):
            st.subheader(f"Table {i}")
            st.caption(f"{len(table.rows)} rows · {len(table.headers)} columns")
            # Integer columns allow duplicate source labels and ragged extraction safely.
            frame = pd.DataFrame(table.rows)
            frame.columns = [f"{c+1}. {table.headers[c] if c < len(table.headers) else 'Extra column'}" for c in range(len(frame.columns))]
            st.dataframe(frame, use_container_width=True, hide_index=True)
    with validation_tab:
        if result.issues:
            st.dataframe([asdict(i) for i in result.issues], use_container_width=True, hide_index=True)
        else:
            st.info("No implemented check raised a finding. Compare the result with the source.")
    with pages_tab:
        st.dataframe([{"page": p.page, "route": p.route, "engine": p.engine,
                       "seconds": round(p.seconds, 2), "attempts": len(p.attempts), "error": p.error}
                      for p in result.pages], use_container_width=True, hide_index=True)
