# Three-minute demo recording script

Use only the included dummy documents. Start with `python run.py`; keep Excel or LibreOffice ready. The following is a script, not a completed video.

| Time | Screen action | Narration |
|---|---|---|
| 0:00-0:20 | Show the upload screen and local OCR engine list | "Truecell converts digital PDFs and scans into Excel locally. It preserves source row provenance and flags uncertainty rather than changing values silently." |
| 0:20-0:45 | Open `samples/C_scanned_inventory.pdf`; show it has no selectable text and 12 columns | "This is an image-only two-page dummy inventory. OCR reconstructs cells from their boxes and detected grid geometry." |
| 0:45-1:15 | Upload C, convert, show progress and joined data | "Each page is processed separately. Compatible tables join across pages, and repeated headers are removed. Genuine duplicate business records stay in the output." |
| 1:15-1:40 | Download/open the workbook; show yellow cells, Page Audit and Provenance | "Yellow cells need review. The audit records attempted strategies, errors and the chosen result. Provenance maps each Excel row to a page and extracted source row." |
| 1:40-2:15 | Convert `B_bank_errors.pdf`; show running_balance and total_mismatch findings | "The numeric columns are called X, Y and Z. The validator discovers the running-balance relation from the contents. It catches the altered balance and wrong total without requiring debit or credit headers. Values are retained and suggested expectations are reported." |
| 2:15-2:40 | Show A's 48 rows and D_stress_50pages's measured report row | "Digital tables avoid OCR where a usable text layer exists. The development set also includes 50 pages, borderless layouts, headerless continuations and degraded scans." |
| 2:40-3:00 | Show `reports/ACCURACY_REPORT.md`, including failures | "These are measured results on our own dummy development set, not a promise for hidden PDFs. Difficult layouts and OCR errors remain visible in the report. Judges can reproduce everything using judge_check." |

Before recording, run the full evaluation. State the actual measured numbers visible in the report. If a scan has errors, show the warning and source comparison instead of claiming perfect extraction. Save the final 2-5 minute recording as `demo.mp4` beside the submission zip.
