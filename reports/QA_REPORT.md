# QA pass — 22 October 2026

Tested on Windows with Python 3.11.9 on 22 October 2026. The counts and artifact hash below come from the final local release gate; these are development checks, not hidden-document accuracy claims.

## Issues found and fixed

| Area | Reproduced issue | Resulting behavior |
|---|---|---|
| OCR recovery | Exceptions from the first engine could stop recovery before the second engine | Other installed engines still run; empty exception messages remain visible; failed pages are not cached as complete |
| Cell evidence | Removing blank/footer rows could shift OCR scores and original readings | Scores/readings follow the actual retained raw row; header rereads use the header's source box |
| Split records | Confidence from a continuation could disappear when joining a page-break row | The joined cell retains the lower recognition score and remains flagged |
| No-table results | Returning early hid the page audit and downloads | Engine audit, errors, Excel and JSON remain accessible |
| Review state | Source-check boxes and notes could carry across documents or proposals | Forms bind to the document snapshot and correction target |
| Missing sources/save failures | A missing source or unwritable workspace could crash review/upload | Errors appear inline; the prior working result and downloads remain available |
| Saved jobs | Missing metadata fields could crash the entire saved-document sidebar | Invalid individual records are skipped; valid jobs remain usable |
| Workspace lifecycle | Saved workspaces had no safe removal control | Each idle workspace has a separate trash action, exact-name confirmation and bounded local deletion; active or locked workspaces are rejected |
| Partial recovery | Failed-page results were labelled complete, hiding resume | Partial jobs remain resumable; edited/reviewed copies are preserved in their existing workspace |
| Startup | Out-of-range ports and retries above 65535 raised socket errors | Invalid ports receive a clear argument error; retry ranges stay valid |
| Edits | Negative indexes could change an unintended last table/column | Invalid or non-integer addresses are rejected before mutation |
| Excel text | Forbidden XML controls could crash export; oversized strings could truncate | Reversible escaping and complete Long Text chunks preserve source text; raw JSON remains unchanged |
| Excel decimals | Very small values could display or underflow to zero | Representable values use suitable formatting; unsafe magnitudes remain exact text |
| Large exports | Repeated worksheet scans and repeated style construction caused excessive work | Row appends and body-style assignments avoid those repeated operations |
| Application shell | The earlier fixed shell did not provide the intended competition presentation | React/TypeScript is now the sole responsive source → grid → validation interface served by local FastAPI |
| Mobile usability | Small controls, a hidden brand descriptor and a 40 MB frontend limit weakened the phone experience | Narrow layouts keep the full brand visible, stack cleanly, retain horizontal table/source inspection, use 44 px touch targets, and match the 50 MB backend limit |
| Validation safety | Proposals and validator experiments needed an inspectable no-save path | Preview and Challenge run on disposable copies; tests and a live fingerprint check confirm the working result is unchanged |
| Re-extraction | Reprocessing an edited or reviewed workspace could overwrite review work | Untouched partial jobs resume verified checkpoints; edited/reviewed jobs fork to a new workspace |
| Multi-page traceability | Continuation joins were visible only in reconstructed output | Every joined table now reports contributing pages, per-page row fragments, removed repeated headers and recovered split rows in the UI and Excel |
| Review workload | Findings and uncertain OCR cells lacked one bounded workflow | A priority queue opens each item at its source and persists checked/reopened state without altering the extraction fingerprint |

## Verification

- **304 Python tests passed**. Ruff check, Ruff format check and dependency consistency passed.
- **16 frontend tests passed**, followed by strict TypeScript checks and a fresh production build. The supplied build needs no Node.js at runtime.
- **23/23** source-bound dummy-document cases passed exact truth checks. Every saved workbook was reopened and compared with its frozen audit at cell, data-type and number-format level; all 46 audit/XLSX artifacts were fresh.
- **5/5** scan cases passed with external Tesseract excluded: inventory, blur/noise, skew, perspective photo and sideways invoice.
- The rebuilt **Windows x64 EXE passed** local health/UI, exact native extraction, bundled RapidOCR, Excel/audit downloads, a path containing spaces and restart recovery. The bundle is **316.71 MiB extracted / 152.53 MiB zipped**; ZIP SHA-256 is `e786bec9bb3fa46d316c964552c82b47f56cf999af38800ae9bb4f65df50b3ea`.
- Public cached regression checks passed their disclosed scope: 35 fuel-table cells, 48 selected census cells plus headers/shapes, a W3C no-table control, and 126 cells plus 14 flattened headers across two public Unicode tables. This does not check every census cell.
- CLI checks returned the expected exit codes for a missing file, identical input/output paths, invalid output suffix, a no-table document and successful native conversion, without tracebacks.
- FastAPI tests covered uploads, no-table downloads, source integrity, edits, reviews, exports, safe workspace deletion, recovery and reprocessing. Frontend unit tests covered API requests and display formatting.
- Docker Compose validation, final image build and live smoke checks passed. The non-root container exposed English/Hindi/Telugu OCR packs and RapidOCR, served the React page, extracted native and scanned samples exactly, returned Excel/CSV/audit downloads, remained healthy and restored its saved workspace after restart. Optional LAN mode is unauthenticated and is for a trusted private network only.
- The offline launcher/model check passed. Browser screenshot interaction and native Excel rendering were not performed.

## Performance scope

The generated `ACCURACY_REPORT.md` is the source for timings from the latest complete evaluation. Timings vary with CPU contention, model startup, OCR engine and document quality; they are not a cross-machine speed guarantee. Peak memory and execution on other operating systems/Python versions were not measured here.

One first portable smoke attempt encountered a transient Windows connection reset while reading an audit response; server logs showed HTTP 200 and an immediate complete rerun passed every portable check. No repeat was reproduced. No live cloud-provider request or hidden-test accuracy claim is included in this QA pass. The final 3:53 demo and current source/evidence archive accompany the submission. External project review materials remain outside this repository.
