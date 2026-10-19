<p align="center">
  <img src="frontend/public/favicon.svg" width="80" height="80" alt="Truecell logo">
</p>

<h1 align="center">Truecell</h1>

<p align="center">
  <strong>Every cell. Accounted for.</strong><br>
  <em>Turn PDFs and scans into validated Excel—with source evidence for every value.</em>
</p>

<p align="center">
  <a href="https://github.com/Pranay207/Truecell/actions/workflows/tests.yml"><img src="https://github.com/Pranay207/Truecell/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <img src="https://img.shields.io/badge/Python-3.10--3.12-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10–3.12">
  <img src="https://img.shields.io/badge/React-19-149ECA?logo=react&amp;logoColor=white" alt="React 19">
  <img src="https://img.shields.io/badge/FastAPI-local_API-009688?logo=fastapi&amp;logoColor=white" alt="FastAPI local API">
  <img src="https://img.shields.io/badge/OCR-offline-0F766E" alt="Offline OCR">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0--or--later-663399" alt="AGPL-3.0-or-later"></a>
</p>

Truecell is a local-first React and FastAPI application built for the **INCUXAI AI Agent Development Challenge 2026**. It detects tables, reconstructs difficult layouts, joins continuations across pages, checks numeric relationships, and exports reviewable Excel workbooks. Every retained value can carry its page, source box, extraction engine, original reading, and confidence evidence.

<p align="center">
  <a href="https://pranay207.github.io/Truecell/demo/"><strong>▶ Watch the 3:53 Product Demo</strong></a><br>
  <sub>See source-linked extraction, validation, correction review, multipage joins, search, and evidence-rich Excel export.</sub>
</p>

![Truecell home screen with local document upload and guided samples](docs/images/truecell-home.png)

*Local-first upload and guided sample workflow.*

![Truecell review workspace with extracted data, source evidence, and validation](docs/images/truecell-evidence.png)

*Searchable extraction, source evidence, validation, and export in one review workspace.*

<details>
<summary>Mobile view (390 px)</summary>

<p align="center">
  <img src="docs/images/truecell-mobile.png" width="390" alt="Truecell responsive mobile upload screen">
</p>

</details>

## Verified Results

| Verified result | Evidence |
|---|---|
| **22/22** deterministic development cases passed | [Accuracy report](reports/ACCURACY_REPORT.md) |
| **222** Python tests and **14** frontend tests passed | [Build verification](reports/BUILD_VERIFICATION.md) |
| **5/5** scan cases passed with Tesseract excluded | [Portable OCR results](reports/PORTABLE_OCR.json) |
| **50 pages / 800 rows / 12 columns** recovered in the measured stress fixture | [Stress PDF](samples/D_stress_50pages.pdf) · [Converted workbook](outputs/D_stress_50pages.xlsx) |
| **18-column** borderless table and vertically grouped nested line items passed exact checks | [18-column workbook](outputs/E_eighteen_columns.xlsx) · [Nested-lines workbook](outputs/E_vertical_nested_lines.xlsx) |
| **126/126 cells** across two public Unicode tables matched their source-pinned reference | [External audit](reports/EXTERNAL_AUDIT.md) |

These are disclosed dummy development fixtures, not blind or hidden-document accuracy claims. Exact evaluation compares ordered cells, headers, table shapes, row multisets, and annotated errors. Start with [JUDGE_START_HERE.txt](JUDGE_START_HERE.txt) for the shortest review path.

## Evaluation criteria coverage

| Evaluation criterion | Verified proof |
|---|---|
| **OCR and extraction accuracy — 30** | **5/5 offline OCR fixtures passed** with Tesseract excluded. Native PDF extraction, RapidOCR, deskew, rotation recovery, and cell-level source boxes. [View OCR evidence](reports/PORTABLE_OCR.json). |
| **Multi-page and complex tables — 25** | **50 pages · 800 rows · 12 columns** recovered in the measured stress fixture. Repeated headers, split rows, 18-column tables, and vertically grouped line items are covered. [View accuracy report](reports/ACCURACY_REPORT.md). |
| **Column alignment and data integrity — 20** | **126/126 public Unicode cells matched** their source-pinned reference. Leading zeros, duplicates, row provenance, safe formulas, and exact header/shape checks are preserved. [View external audit](reports/EXTERNAL_AUDIT.md). |
| **Automation and error recovery — 15** | Automatic page routing, alternate extraction strategies, resumable checkpoints, arithmetic validation, correction previews, and review history. [View QA evidence](reports/QA_REPORT.md). |
| **Code quality and usability — 10** | **222 Python + 14 frontend tests passed.** Responsive React UI, FastAPI backend, offline operation, searchable tables, saved workspaces, and multi-platform CI. [View build verification](reports/BUILD_VERIFICATION.md). |

## Run Truecell

### 1. Windows portable — easiest

Use the supplied `Truecell-Portable-Windows-x64.zip` on **Windows 10/11 x64**:

1. Extract the complete ZIP.
2. Double-click `Truecell.exe` inside `Truecell-Portable`.
3. Truecell opens automatically in the default browser.

Python, Node.js, an API key and internet access are not required. The portable folder includes the React application, local FastAPI server, RapidOCR, OCR models and demo PDFs. Saved documents remain beside the executable in `TruecellData`; keep the entire extracted folder together. The console window shows the local address and stops the server when closed.

The tested portable bundle is a PyInstaller one-folder application: **316.41 MB extracted / 152.36 MB zipped**. Its packaged EXE passed health and UI checks, exact native-PDF extraction, a RapidOCR scan with external Tesseract disabled, Excel/audit downloads, launch from a path containing spaces, and workspace persistence after restart. See [portable instructions](portable/README-FIRST.txt).

### 2. Python/source launcher

Use **64-bit Python 3.10–3.12** when running from source. Python 3.11 on Windows is the locally tested platform.

```text
Windows:       double-click START_TRUECELL.cmd
Linux/macOS:   bash start.sh
```

The first source run creates `.venv` and installs pinned dependencies, so it needs internet. Later runs and normal conversions work offline on CPU without an API key or GPU. The launcher opens a local URL, normally **http://127.0.0.1:8501**.

```powershell
# Verify an existing installation without network access
.\START_TRUECELL.cmd --check --offline

# Start using installed packages only
.\START_TRUECELL.cmd --offline

# Optional phone demo on the same private Wi-Fi
.\START_TRUECELL.cmd --offline --lan
```

The application accepts PDFs up to **200 pages**, multi-frame images/TIFFs up to **50 frames**, and uploads up to **50 MB**. The measured large-document fixture is 50 pages; the 200-page ceiling is an input capability, not a 200-page accuracy benchmark. The production frontend is prebuilt, so judges do not need Node.js.

<details>
<summary>Manual setup and CLI</summary>

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install --use-feature=truststore -r requirements.txt
python run.py
```

```sh
python convert.py samples/A_invoice_register.pdf -o outputs/demo.xlsx
python convert.py samples/B_bank_errors.pdf -o outputs/bank.xlsx --verify
python convert.py scan.pdf -o outputs/scan.xlsx --force-ocr
```

`--verify` runs an independent local OCR check on native pages. `--force-ocr` handles damaged text layers. `python run.py --lan` serves the app only to loopback and the detected private network while the process is running.

</details>

<details>
<summary>Build and verify the Windows portable release</summary>

```powershell
# Requires the source development environment; end users do not run this.
.\BUILD_PORTABLE.cmd
.\.venv\Scripts\python.exe scripts\smoke_portable.py
```

The build uses pinned packages from `requirements-build.txt`, writes ignored artifacts under `portable-release/`, and creates a per-file `SHA256SUMS.txt`. The portable ZIP is a release artifact rather than a source-controlled binary.

</details>

## Sample PDFs and converted Excel files

Every document below contains generated dummy data. The linked XLSX files are Truecell outputs; independent truth files remain beside the PDFs in `samples/`.

| Case | Input PDF | Converted Excel | What it proves |
|---|---|---|---|
| Invoice register | [PDF](samples/A_invoice_register.pdf) | [XLSX](outputs/A_invoice_register.xlsx) | 12 columns joined across 3 pages |
| Bank errors | [PDF](samples/B_bank_errors.pdf) | [XLSX](outputs/B_bank_errors.xlsx) | Two injected arithmetic errors detected |
| Scanned inventory | [PDF](samples/C_scanned_inventory.pdf) | [XLSX](outputs/C_scanned_inventory.xlsx) | Offline OCR across 2 scanned pages |
| Scanned continuations | [PDF](samples/F_scanned_multipage_continuations.pdf) | [XLSX](outputs/F_scanned_multipage_continuations.xlsx) | 5 raster-only pages, 12 columns, repeated headers and two split-row joins |
| Stress document | [PDF](samples/D_stress_50pages.pdf) | [XLSX](outputs/D_stress_50pages.xlsx) | 50 pages, 800 rows, repeated-header removal |
| Wide borderless table | [PDF](samples/E_eighteen_columns.pdf) | [XLSX](outputs/E_eighteen_columns.xlsx) | 18-column alignment |
| Nested line items | [PDF](samples/E_vertical_nested_lines.pdf) | [XLSX](outputs/E_vertical_nested_lines.xlsx) | Vertically spanned group labels with source evidence |

## Measured benchmark

Measured locally on Windows, Python 3.11.9. Times are wall-clock observations and can vary by CPU and OCR engine.

| Development fixture | Pages | Rows | Columns | Time | Exact result |
|---|---:|---:|---:|---:|---|
| Invoice register | 3 | 48 | 12 | 1.36 s | PASS |
| Bank errors | 1 | 19 | 6 | 0.34 s | PASS, 2/2 errors caught |
| Scanned inventory | 2 | 24 | 12 | 32.96 s | PASS |
| 5-page scanned continuations | 5 | 33 | 12 | 174.97 s | PASS, 2/2 split rows joined |
| 50-page stress | 50 | 800 | 12 | 118.00 s | PASS |
| 18-column table | 1 | 9 | 18 | 3.69 s | PASS |
| Vertical nested lines | 1 | 8 | 10 | 0.11 s | PASS |

See all 22 cases, definitions, and per-page timings in the [accuracy report](reports/ACCURACY_REPORT.md).
The five-page raster benchmark selected local Tesseract and took about three minutes on this host. The separate portable suite excludes Tesseract and remains 5/5 on its five disclosed scan fixtures; do not infer RapidOCR performance for the new stress case.

## Demo

1. Start Truecell and choose **Find a wrong balance**.
2. Open **Review**, select a priority item, and jump to its exact source page and cell. Mark it checked only after inspection.
3. Open **Equations** and inspect printed `1081.00`; Truecell proposes `1064.00` using two adjacent balance equations.
4. Preview the proposal and verify that it clears two equation failures without changing saved data. Apply it only after source review and entering a reason.
5. Open the invoice sample and show its join receipt: contributing pages, repeated headers removed, split rows recovered, and rows read per page.
6. Export Excel, then show the Data, Cell Evidence, Validation Report, Join Receipt, Constraints, Page Audit, and Verification sheets.

Use the prepared [3–4 minute recording script](docs/DEMO_SCRIPT.md) for the full walkthrough.

## How it works

```mermaid
flowchart LR
    A[PDF or image] --> B[Validate and route pages]
    B --> C[Native text and grid extraction]
    B --> D[Render, deskew and offline OCR]
    C --> E[Rank table candidates]
    D --> E
    E --> F[Recover and join continuations]
    F --> G[Validate structure and arithmetic]
    G --> H[Review cells against source]
    H --> I[Excel and audit JSON]
```

The agent chooses page-level strategies from document evidence, reconstructs tables, preserves source coordinates, joins only compatible adjacent tables, and validates the assembled result. Each assembled table carries a join receipt showing which pages and row fragments contributed to it. Running-balance and `a*b=c` / `a+b=c` relations are inferred from repeated numeric patterns instead of relying on financial column names. Proposed repairs remain unapplied until a reviewer inspects the source and supplies a reason.

Search filters large extracted tables across every column while preserving original row identities for evidence and edits. The bounded review queue puts rule findings and the lowest OCR-confidence cells first, opens their source location, and remembers checked/reopened state without changing the extraction fingerprint. Saved workspaces keep the source, extraction, corrections, and review history together under `outputs/jobs/`.

<details>
<summary>Extraction and recovery details</summary>

- Native ruled geometry is preferred when structurally trustworthy; borderless reconstruction uses whitespace, fonts, stable numeric columns, and separated horizontal streams.
- Scans use grid-aware recognition, contrast enhancement, deskew, rotation recovery, optional isolated rereads, and perspective correction. OCR coordinates are mapped back to the original page.
- Repeating headers are removed, business rows are never silently deduplicated, split records can retain evidence from both pages, and carry-forward summaries stay outside transaction rows.
- Completed-page checkpoints bind to source bytes, code, packages, model assets, and options. Changed or corrupt checkpoints are recomputed. Failed pages are logged while later pages continue.
- The bundled English model provides portable RapidOCR. Tesseract is used when installed. Optional cloud vision requires both `--allow-cloud` and explicit credentials; it was not used for the reported results.

</details>

## What the Excel workbook contains

| Sheet | Contents |
|---|---|
| `Data 1`, `Data 2`, … | Reconstructed tables with safe typing and source-evidence links |
| `Validation Report` | Structural, arithmetic, OCR, and ambiguity findings |
| `Cell Evidence` | Page, bounding box, engine, reading, alternate reading, and score |
| `Join Receipt` | Contributing pages, page joins, repeated headers removed, split rows recovered, and source-row counts |
| `Page Audit` | Extraction attempts, selected strategy, timing, and failures |
| `Provenance` | Row-to-page mapping, including split records |
| `Constraints` / `Repair Proposals` | Inferred equations, agreement, violations, and unapplied candidates |
| `Correction History` | Explicit human edits, reasons, timestamps, and chained hashes |
| `Verification` / `Read me` | Source hashes, review status, coverage counts, and interpretation notes |

Identifiers and leading zeros remain text. Unambiguous numbers and dates are typed. Strings beginning with `=` remain text, so source content is never executed as an Excel formula. Long and XML-forbidden text uses a documented reversible export convention.

## Reproduce the evidence

```sh
python -m pytest -q
python scripts/verify_recorded_outputs.py
python scripts/judge_check.py
python scripts/portable_ocr_check.py

# Frontend development checks require Node.js 22.12+
npm --prefix frontend test
npm --prefix frontend run build
```

The public-source audit is separate because fetching its published fixtures requires network access:

```sh
python scripts/public_audit.py --fetch
```

<details>
<summary>Reports and evaluation scope</summary>

- [Development accuracy](reports/ACCURACY_REPORT.md): all 22 generated cases and timings.
- [External layout audit](reports/EXTERNAL_AUDIT.md): a 35-cell fuel table, 48 selected census cells plus all 16 headers and both shapes, a no-table control, and two complete public Unicode tables with 126/126 data cells and 14/14 flattened headers. The remaining census cells are outside the annotation scope.
- [External published-fixture audit](reports/TRANSFER_AUDIT.md): exact cell, header, and shape regression checks on three public dummy fixtures and their author-provided expected results. Source and scope are documented in the report.
- [Build verification](reports/BUILD_VERIFICATION.md): tests, portability checks, and explicitly unverified items.

`python -m eval.generate_samples --hard` and `python -m eval.generate_layouts` regenerate the dummy sources and truth. Scoring canonicalizes numeric formatting and whitespace while preserving leading zeros. A no-table control passes only when no table is invented.

</details>

## Limitations

- Handwriting, untested scripts, broken glyph maps, severe cropping, overlapping text, and extreme perspective may fail.
- Native, explicitly ruled vertical body spans are supported conservatively. OCR/unruled spans and arbitrary multi-axis merged structures remain ambiguous.
- Headerless joins can confuse unrelated tables with similar geometry. Sparse data may not provide enough evidence for arithmetic inference, while coincidental relations can create false alarms.
- OCR confidence and arithmetic agreement are evidence, not guarantees. A clean validation report does not prove correct extraction; important values still require source review.
- English total vocabulary is limited, and OCR engines can share the same mistake.

## Project and license

`truecell/` contains the extraction engine and FastAPI application, `frontend/` contains the React/TypeScript interface and production build, `eval/` generates and scores dummy documents, `samples/` contains PDFs and truth, `outputs/` contains converted workbooks, and `reports/` records measured evidence.

Project-specific code is licensed **AGPL-3.0-or-later**. Third-party libraries and models are credited in [THIRD_PARTY.md](THIRD_PARTY.md). No application source from the external fixture repository is included; all documents committed under `samples/` contain generated dummy data.
