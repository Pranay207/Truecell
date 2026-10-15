# Accuracy and validation report

Measured on deterministic, self-generated dummy development documents. These numbers are not independent benchmarks and do not guarantee hidden-PDF accuracy.

Cell precision/recall compare canonicalized values at exact table/row/column coordinates. Numeric formatting and whitespace are normalized; leading zeros are preserved. Row match uses a multiset, so duplicate records are counted. PASS requires exact cells, headers, shape and detection of every injected error.

Evaluation host: Python 3.11.9, Windows AMD64. Timings are local wall-clock measurements and can include concurrent system activity. Peak memory was not benchmarked.

| Problem case | Cell P | Cell R | Exact | Rows | Headers | Shape | Tables | Errors caught | s/page | Result |
|---|---:|---:|---:|---:|---:|---|---|---|---:|---|
| A_invoice_register | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.21 | PASS |
| B_bank_errors | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 2/2 | 0.16 | PASS |
| C_scanned_inventory | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 37.81 | PASS |
| D_blur_noise | 82.6% | 82.6% | 82.6% | 0.0% | 100.0% | True | True | 0/0 | 70.89 | FAIL |
| D_borderless | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 1.48 | PASS |
| D_headerless | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 1.50 | PASS |
| D_merged_wrapped | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.06 | PASS |
| D_mixed | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 4.52 | PASS |
| D_phone_photo | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 69.79 | PASS |
| D_skew_5deg | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 9.23 | PASS |
| D_split_row | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.05 | PASS |
| D_stress_50pages | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.89 | PASS |
| D_two_tables | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | True | True | 0/0 | 0.12 | PASS |

## Known limitations / failures

- OCR confidence is not a calibrated accuracy probability. High-confidence digit mistakes can still occur.
- Borderless segmentation, merged body cells, two unrelated tables with similar geometry, and cross-page wrapped records can remain ambiguous. Values are retained for review; no business-row deduplication is performed.
- Arithmetic inference needs enough varied rows and a strong majority. Checks may be skipped on short/heterogeneous tables. Candidate selection can prefer a larger but wrong table; all disagreements are audited.
- Ambiguous day/month dates and comma-decimal numeric strings remain text. Structural total inference and multilingual total vocabularies are limited.
- Phone-photo perspective, extreme rotation and handwritten text are not guaranteed.
- The optional network vision pass requires explicit configuration and is not part of offline baseline metrics.

Available OCR engines in this run: tesseract, rapidocr. Page Audit records which was selected. A machine with only RapidOCR can produce different accuracy and runtime.

The bank sample contains two injected source errors. An altered balance can raise findings on both the altered row and its successor because each printed balance is checked against the previous printed balance. Review findings also include expected layout/uncertainty notices and are not a count of proven extraction errors.

Observed failing cases: D_blur_noise.
