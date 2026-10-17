# External document audit

4 public aggregate/dummy PDFs from three independently maintained source projects, with source hashes and explicit annotation scope in `eval/public_cases.json`. Expectations were transcribed from rendered source pages; the Unicode two-table case is also bound to its publisher's paired CSV by checksum and an exact row comparison. These inputs were used to discover and repair failures, so they are development regressions rather than a blind benchmark. No source PDF or external application implementation is redistributed.

| Case | Scope | Checked cells | Headers | Shape | Result |
|---|---|---:|---|---|---|
| camelot-fuel-table | full | 35/35 | True | True | PASS |
| census-two-table-checkpoints | checkpoints | 48/48 | True | True | PASS |
| w3c-document-without-table | empty | 0/0 | True | True | PASS |
| tabula-unicode-two-tables | full | 126/126 | True | True | PASS |

The fuel table checks all 35 data cells and seven flattened headers. The census page checks **48 selected data cells**, all 16 headers, both table counts/shapes (32×10 and 32×6), and uniqueness of selected row labels; its other 464 data cells are outside the annotation scope. The Unicode case checks two complete tables: all **126 data cells**, all 14 flattened headers, both shapes, Japanese text, multiline cells, spanning headers, and negative-triangle notation. The W3C fixture checks that no table is invented. Do not describe these checks as whole-document OCR accuracy.

The first saved development outputs failed the fuel table and census layouts; their measurements remain in the JSON when present. Header-span handling, numeric text-fragment joining and separated borderless streams were repaired with general geometry rules. The old engine state was not a tagged release; first observations are historical evidence, not a reproducible old-version benchmark.

Unmapped text-layer glyphs, handwriting and arbitrary damaged scans remain limitations. Explicitly ruled vertical group spans in native-PDF body rows are supported conservatively; OCR/unruled spans and arbitrary multi-axis nested merges remain ambiguous. Inferred structure and header re-readings remain flagged.

Reproduce: `python scripts/public_audit.py --fetch` on the first run, then omit `--fetch` for verified cached sources. This command makes network requests only with `--fetch`. The ordinary converter is offline unless cloud verification is explicitly enabled.

- camelot-fuel-table: https://raw.githubusercontent.com/camelot-dev/camelot/92777b852e00933a5c4b9ba642601784604356cd/tests/files/foo.pdf (SHA-256 `7d6c24e45b38375e322419281cee1335ddb97e00fc86abe9f22afcd8b42e6d82`)
- census-two-table-checkpoints: https://raw.githubusercontent.com/tabulapdf/tabula-java/2cdf3b4fd3f7e921dca8cc6814cdd9316be40f0f/src/test/resources/technology/tabula/12s0324.pdf (SHA-256 `092853e4af150d1c72f474a59ce902305e8675c1d04059d5e2af4a628bc6dfbd`)
- w3c-document-without-table: https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf (SHA-256 `3df79d34abbca99308e79cb94461c1893582604d68329a41fd4bec1885e6adb4`)
- tabula-unicode-two-tables: https://raw.githubusercontent.com/tabulapdf/tabula-java/2cdf3b4fd3f7e921dca8cc6814cdd9316be40f0f/src/test/resources/technology/tabula/twotables.pdf (SHA-256 `72a9d20672e4d581ae9933a07cbe9a6f6db40632218fb7e73bd923dee033d8cd`)
  - Published reference CSV: https://raw.githubusercontent.com/tabulapdf/tabula-java/2cdf3b4fd3f7e921dca8cc6814cdd9316be40f0f/src/test/resources/technology/tabula/csv/twotables.csv (SHA-256 `9fa47b7f1d16d2d16afdc8544fc1a67d078690cc08b091a5a51425940af99c6c`)
