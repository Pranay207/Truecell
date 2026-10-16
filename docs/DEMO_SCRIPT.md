# Truecell Studio — 3–4 minute recording script

Record the real app at 1080p with readable zoom. Use supplied dummy files. Open the app and the bank sample's exported workbook beforehand. Do not claim this script is a recorded video. Allow conversion time to appear or clearly label any time cut.

**0:00–0:25 — Problem and scope.** “Extracting numbers is only half the job. Truecell lets us inspect where each value came from and why the numbers look suspicious. This runs locally on CPU, without an API key.” Show the upload control, 50-page scope and available OCR engines. Click **Find a wrong balance**.

**0:25–1:15 — Diagnose without meaningful headers.** Show opaque bank headers. Open **Equation receipts**. “It inferred a running-balance relationship from repeated values. This printed balance breaks the equation for this row and the next.” Show data row 11, column 6: `1081.00`, the `1064.00` proposal and its two supporting equation instances. Show the outlined original source cell. Explain that the source document itself contains this error.

**1:15–1:50 — Preview and explicitly review.** Click **Preview the effect without saving** and show two failed checks becoming zero. “This is a counterfactual, not an automatic edit.” Confirm the working value is still `1081.00`. Check the source-inspection box, enter “Arithmetic correction after source review; original printed value retained,” and apply. Show **Correction History** in Review & export and download the immutable original extraction. Explain that the separate wrong total remains a finding.

**1:50–2:20 — Show the validator's limits.** Open the invoice sample, then **Challenge lab → Run controlled error injections**. “This hides headers and perturbs sampled numbers in copies. It invokes the same validator used for real conversion.” Show actual detected/missed counts and unmodeled columns. The observed development run detected 14/24; read whatever the live run reports. Do not call this OCR accuracy.

**2:20–2:55 — Hard extraction and workbook evidence.** Show the supplied skewed scan and original PDF. Show its recovered 12-column table and source inspector. Open a prepared export: Data, Cell Evidence, Validation Report, Page Audit, Constraints and Verification. Ctrl+click a linked value to its evidence row. Explain that original readings remain and source formulas are not executed.

**2:55–3:30 — Reproducible results and limits.** Show `reports/ACCURACY_REPORT.md`: 13/13 deterministic development cases, including 50 pages/800 rows. Show the external audit's scope: all 35 fuel-table cells, only 48 selected census cells, a no-table control. “These were development inputs, not unseen accuracy measurements.” Show saved workspaces/resume and point to setup instructions/source code.

**3:30–3:45 — Deliverable.** Show a downloaded workbook and its Unreviewed or explicitly reviewed snapshot status. “The deliverable is structured Excel with the evidence needed to inspect it.” Stop recording. Save an MP4, play it back, check audio/readability and keep the duration between 2 and 5 minutes.

Use the organizer's actual upload destination. The announcement's link/contact are placeholders. Submit the source ZIP, README, reports, sample pairs and actual video file/link.
