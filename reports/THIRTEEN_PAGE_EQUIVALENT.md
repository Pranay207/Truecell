# Disclosed 13-page equivalent evaluation

This is a **synthetic development fixture created by the Truecell project**. It is not the missing private 13-page document mentioned by an external review, and it must not be presented as a blind or organizer-supplied result.

## Fixture

- Source: `samples/G_thirteen_page_equivalent.pdf`
- SHA-256: `5d57669d0fcebb61dc7ef513ba319e4a4ba760c4d812c68120423368f71b2c15`
- 13 pages
- 4 logical tables
- 14 columns per table
- 78 data rows
- 1,092 expected data cells
- Full-width document titles, wrapped cell text, repeated page headers and multi-page continuations

## Exact result

| Check | Result |
|---|---:|
| Table count | Exact |
| Table shapes | Exact |
| Headers | 100% |
| Rows | 100% |
| Data cells | 1,092/1,092 (100%) |
| Non-empty headers and data cells with source boxes | 1,148/1,148 (100%) |
| Semantic type mismatches | 0 |
| Review findings | 13 |

The 13 review findings are intentional full-width-title notices, one on each correct source page. They show that the title was retained as document context rather than incorrectly prefixed to all 14 column headers.

The verified output is `outputs/G_thirteen_page_equivalent.xlsx`; its source-bound audit is `outputs/G_thirteen_page_equivalent.audit.json`. `tests/test_equivalent_fixture.py` checks the fixture contract and re-scores the saved audit exactly.

## Interpretation

This fixture closes a reproducible regression gap for a 13-page, four-table, wide-column layout. It does not prove universal document accuracy. Independent claims must use the truth-separated process in `docs/BLIND_EVALUATION.md` with documents not used during development.
