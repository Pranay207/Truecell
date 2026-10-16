# External published-fixture audit

This report evaluates only the Truecell engine against three public dummy PDFs and their author-provided expected results from [damnlens-ai-agent](https://github.com/rayanakarthikeyan/damnlens-ai-agent) at commit `9fb9116422ed4685e97ff8de6a95c01cc4788575`. The source repository's application code was not run, and its fixture files are not included in Truecell. Because these fixtures informed later development, the results are regression checks rather than a blind evaluation.

| Fixture | Checked data cells | Exact cells | Headers | Shape | Result |
|---|---:|---:|---:|---|---|
| 01_invoice_register.pdf | 372 | 100.00% | 100.00% | True | PASS |
| 02_scanned_inventory.pdf | 240 | 100.00% | 100.00% | True | PASS |
| 03_bank_statement.pdf | 252 | 100.00% | 100.00% | True | PASS |

Historical first observations, when supplied, are preserved in the JSON. The earlier engine state was not a tagged release; those measurements are historical, not a reproducible old-version comparison. Scoring canonicalizes numeric formatting and whitespace while requiring ordered table/row/column matches. Financial-source error recall is not scored here because this external truth file does not annotate injected errors.

Reproduce after obtaining the public samples directory from the cited source: `python scripts/transfer_audit.py --fixtures PATH_TO_SAMPLES`. The audit script invokes only Truecell application code.
