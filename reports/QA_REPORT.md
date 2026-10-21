# QA pass - 17 October 2026

Tested on Windows with Python 3.11.9. This pass covers the current source folder; the source/evidence archive was rebuilt from the reviewed Git-tracked allowlist on 19 October 2026.

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

- **260 Python tests passed** in the development environment. Ruff checks and formatting passed, and dependency checks passed in the recorded environments.
- The packaged Windows EXE passed a separate portable smoke test covering local health/UI, exact native extraction, bundled RapidOCR, Excel/audit downloads, a path containing spaces and saved-workspace recovery after restart.
- **15 frontend tests passed**, including extracted-row search, original-index preservation, OCR-language upload options and snapshot-safe review requests; strict TypeScript checks passed, and the Vite production bundle rebuilt successfully. The supplied build needs no Node.js at runtime.
- **23/23** committed dummy-document outputs passed source-hash and exact-score verification. The five-page raster-only, 12-column continuation fixture passed Tesseract/RapidOCR cross-checking with all 33 rows, four repeated headers removed and two split rows recovered. The disclosed 13-page equivalent matched all 1,092 data cells. A no-table control passes only with zero output tables; its cell percentages are n/a.
- **5/5** scan cases passed with Tesseract excluded: inventory, blur/noise, skew, perspective photo and sideways invoice. See `PORTABLE_OCR.json` for the engine-isolation method and measured timings.
- Public cached regression checks passed their disclosed scope: 35 fuel-table cells, 48 selected census cells plus headers/shapes, a W3C no-table control, and 126 cells plus 14 flattened headers across two public Unicode tables. This does not check every census cell.
- The recorded readback audit predates the vertical-span case and checked the original **20 converted workbooks** for row counts, headers, source hashes, **1,067 identifier cells**, and absence of formula-type cells. Those workbooks contain 13,225 data-cell positions; that count is not an independent accuracy measurement.
- CLI checks returned the expected exit codes for a missing file, identical input/output paths, invalid output suffix, a no-table document and successful native conversion, without tracebacks.
- FastAPI tests covered uploads, no-table downloads, source integrity, edits, reviews, exports, safe workspace deletion, recovery and reprocessing. Frontend unit tests covered API requests and display formatting.
- The modern local server returned HTTP 200 for health, the React page, hashed assets, a source-page image, Excel and audit JSON. Optional LAN mode also returned HTTP 200 through its exact private-network address while retaining localhost access. A live bank extraction produced 19 rows × 6 columns; preview removed two failed equation checks in a disposable copy, Challenge caught 22/24 controlled edits, and the saved fingerprint/value stayed unchanged.
- The offline launcher/model check passed. Browser screenshot interaction and native Excel rendering were not performed.

## Performance scope

The final export-only check on the 50-page/800-row audit took **9.083 seconds**. An isolated two-page perspective-photo conversion, including Excel export, took **16.760 seconds** and passed all expected cells, headers and shapes.

The fresh five-page raster-only continuation conversion took **174.97 seconds** with local Tesseract on this host (about **34.99 seconds/page**) and passed its exact source-bound checks. This is a single-machine development measurement.

Concurrent OCR testing produced a much slower photo run, retained in the raw benchmark reports. Timings vary with CPU contention, model startup and document quality; they are not a cross-machine speed guarantee. Peak memory and execution on other operating systems/Python versions were not measured here.

No live cloud-provider request or hidden-test accuracy claim is included in this QA pass. The final 3:53 demo and current source/evidence archive accompany the submission. External project review materials remain outside this repository.
