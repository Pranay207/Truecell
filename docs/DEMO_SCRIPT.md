# Truecell — updated 3:53 demo script

This is the recording plan for the published 1080p demo. It uses only supplied dummy fixtures and separates measured development results from blind evaluation.

**0:00–0:18 — Problem, product and privacy.** Introduce Truecell as a local workflow that turns difficult PDFs and scans into reviewable spreadsheet data with source evidence. Show the home page, local-engine status and upload panel. Explain why a plausible misplaced value makes extraction alone insufficient.

**0:18–0:39 — Intake, page profiling and routing.** Show the supported PDF and image inputs, 200-page PDF ceiling and extraction options. Explain that Truecell profiles scripts, text health, blur, skew, rotation, perspective and table likelihood. Native PDF strategies, bundled RapidOCR and installed Tesseract create candidates whose ranks and selection reasons are retained in Page Audit.

**0:39–1:00 — Review by priority, at the source.** Open **Find a wrong balance**. Show its **Needs review** state, priority queue and exact cell evidence. Selecting a finding visibly connects the table cell to its original page, source box, reading, engine, alternatives and confidence context.

**1:00–1:41 — Validate, preview and review.** Open **Equations**. Show the inferred running-balance relationship, printed `1081.00`, proposed `1064.00` and two supporting equation instances. Preview the validation impact on a disposable copy, confirm saved data has not changed, then apply a reasoned correction after source inspection. Show correction history and the Reviewed export gate.

**1:41–2:10 — Difficult table reconstruction.** Show the five-page raster continuation: 12 columns, four repeated headers removed and two split rows recovered. Open its join receipt. Then show wide, merged, wrapped and source-backed vertical-group examples; ambiguous nesting is routed to review rather than guessed.

**2:10–2:25 — Search without losing evidence.** In the 50-page / 800-row fixture, search for `invoice 800`, jump to page 50 and highlight the source. Explain that filtering retains the original row identity and evidence link.

**2:25–2:43 — Honest states and recovery.** Show complete, partial, failed, needs-rescan, needs-review and reviewed states. Explain page-level continuation, source-bound checkpoints and saved local workspaces that retain extraction, corrections and history across restarts.

**2:43–2:59 — Delivery with evidence.** Show Excel, CSV, JSON and local API outputs. In the workbook, show Data, Cell Evidence, Validation Report, Join Receipt, Page Audit, Constraints, Provenance, Correction History and Verification. Linked spreadsheet cells lead to their evidence row.

**2:59–3:39 — Reproducible evidence and delivery options.** Show the current measured results: 23/23 source-bound development cases, 5/5 RapidOCR scan fixtures with Tesseract excluded, 126/126 public Unicode cells, 50 pages / 800 rows / 12 columns, and the 13-page / four-table / 1,092-cell synthetic case. State clearly that these are disclosed development results, not universal or unseen-document accuracy claims. Show the truth-withheld blind-evaluation workflow and Windows, Python and Docker delivery. The verified build passed 304 Python and 16 frontend tests.

**3:39–3:53 — Close.** Summarize the single local workflow: extraction, validation, source evidence, human review and recovery. End with **Truecell. Every cell, accounted for.**

The published video is at <https://pranay207.github.io/Truecell/demo/> with English captions and a direct MP4 download.
