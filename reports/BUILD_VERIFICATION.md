# Build verification

The application was built and executed locally with Python 3.11 on Windows. Pinned direct dependencies and the resolved test environment are included in `requirements.txt` and `requirements-lock.txt`.

- A separate clean virtual environment installed the documented dependencies successfully. `pip check` found no broken requirements.
- **84 tests passed** in both the development environment and the separately installed clean environment. The suite covers digital end-to-end extraction, two deliberate financial errors under opaque headers, typed Excel export and formula safety, preservation of duplicate records, merged headers, split rows, headerless joins, image geometry, skew correction, perspective detection, malformed inputs, the 50-page limit, failed-page continuation, optional-model schema checks, scorer penalties, and Streamlit application rendering.
- The documented CLI ran successfully from the clean environment on the three-page digital invoice and a mixed digital/scanned PDF. Mixed-row engine provenance was checked against the source page route.
- The Streamlit server returned HTTP 200 from its health endpoint. Application-level UI tests passed for the initial upload form and a result containing duplicate headers and ragged rows. No native browser surface was available for browser screenshot QA.
- Sample PDFs were rendered with PyMuPDF because Poppler was unavailable. The invoice, bank statement, scanned inventory and merged/wrapped-header examples were visually inspected. Approximate workbook previews were inspected for all five sheet types, and saved cell types, leading zeros, formula-injection protection and financial-error highlights were checked with openpyxl. These are not native Excel recalculation tests; exported workbooks contain no source formulas.
- All 13 dummy PDFs have ground-truth JSON/Excel and converted Excel/audit pairs. Exact-match failures remain in `ACCURACY_REPORT.md`. Timings reflect the local machine and concurrent activity, not a standardized performance benchmark.

Final measured result: **12 of 13 exact cases passed**. `D_blur_noise` remains a failure at **82.64% coordinate-level cell match**. The three baseline documents, perspective-photo case, and 50-page/800-row stress case pass. Both deliberate bank errors were detected. These are development-set results, not a hidden-document accuracy claim.

Not verified here: live vision API requests (no provider credentials used), execution on macOS/Linux or Python 3.10/3.12 (a CI matrix is supplied), independent hidden-document accuracy, and a recorded demo video. `docs/DEMO_SCRIPT.md` supplies the requested recording script.
