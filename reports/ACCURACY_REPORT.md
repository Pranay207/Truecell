# Accuracy and validation report

Measured on deterministic, self-generated dummy development documents. These numbers are not independent benchmarks and do not guarantee hidden-PDF accuracy.

Cell precision/recall compare canonicalized values at exact table/row/column coordinates. Numeric formatting and whitespace are normalized; leading zeros are preserved. Row match uses a multiset, so duplicate records are counted. PASS requires exact cells, headers, shape and detection of every injected error.
No-table controls show n/a for cell/row/header percentages; passing requires no extra table. They do not contribute fabricated cell matches.

Evaluation host: Python 3.11.9, Windows AMD64. Timings are local wall-clock measurements and can include concurrent system activity. Peak memory was not benchmarked.

| Problem case | Cell P | Cell R | Exact | Rows | Headers | Shape | Tables | Errors caught | s/page | Result |
|---|---:|---:|---:|---:|---:|---|---|---|---:|---|
| A_invoice_register | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.36 | PASS |
| B_bank_errors | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 2/2 | 0.13 | PASS |
| C_scanned_inventory | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 8.79 | PASS |
| D_blur_noise | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 16.59 | PASS |
| D_borderless | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.78 | PASS |
| D_headerless | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.62 | PASS |
| D_merged_wrapped | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.02 | PASS |
| D_mixed | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 2.04 | PASS |
| D_phone_photo | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 11.60 | PASS |
| D_skew_5deg | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 5.84 | PASS |
| D_split_row | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.01 | PASS |
| D_stress_50pages | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.60 | PASS |
| D_two_tables | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.04 | PASS |
| E_eighteen_columns | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 3.69 | PASS |
| E_no_table_letter | n/a | n/a | n/a | n/a | n/a | True | True | 0/0 | 0.07 | PASS |
| E_page_carry | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.05 | PASS |
| E_sideways_invoice | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 22.01 | PASS |
| E_sparse_schedule | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.02 | PASS |
| E_unruled_totals | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.04 | PASS |
| E_vertical_nested_lines | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.11 | PASS |
| E_wrapped_contacts | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.03 | PASS |

## Known limitations / failures

- OCR confidence is not a calibrated accuracy probability. High-confidence digit mistakes can still occur.
- Explicitly ruled vertical group spans in native-PDF body rows are supported conservatively. OCR/unruled spans, arbitrary multi-axis nested merges, borderless segmentation, two unrelated tables with similar geometry, and cross-page wrapped records can remain ambiguous. Values are retained for review; no business-row deduplication is performed.
- Arithmetic inference needs enough varied rows and a strong majority. Checks may be skipped on short/heterogeneous tables. Inferred relations can be coincidental. Candidate selection prioritizes trusted native grid geometry but can still select the wrong layout; disagreements are audited.
- Ambiguous day/month dates and comma-decimal numeric strings remain text. Structural total inference and multilingual total vocabularies are limited.
- Phone-photo perspective, extreme rotation and handwritten text are not guaranteed.
- The optional network vision pass requires explicit configuration AND opt-in and is not part of offline baseline metrics.

Available OCR engines in this run: tesseract, rapidocr. Page Audit records which was selected. A machine with only RapidOCR can produce different accuracy and runtime.

The bank sample contains two injected source errors. An altered balance can raise findings on both the altered row and its successor because each printed balance is checked against the previous printed balance. Review findings also include expected layout/uncertainty notices and are not a count of proven extraction errors.
Source-cell boxes, equation receipts, and counterfactual repair proposals are exported alongside the data. No proposal is applied in this benchmark. Header re-readings remain flagged even when they improve transcription. Human review status starts as Unreviewed.

The separate Challenge lab deliberately perturbs numeric cells in copies of this extraction and reports detected AND missed edits. It tests validation sensitivity, not OCR accuracy; unmodeled columns can miss every edit.

Observed failing cases: none in this evaluated subset.
