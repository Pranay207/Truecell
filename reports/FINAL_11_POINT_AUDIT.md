# Final 11-point capability audit

**Audit date:** 22 October 2026

**Scope:** current Truecell source tree, tests, recorded development evidence and delivery scripts

**Method:** source inspection mapped each requested capability to executable code and focused tests. This is an engineering audit, not an independent accuracy certification.

## Verdict

Truecell contains working engineering paths for points 1 through 10. Point 11 contains a complete two-stage, tamper-evident blind-evaluation harness, but the actual independent evaluation remains pending until a third party supplies unseen authorized documents and keeps truth unavailable during extraction.

Therefore, the accurate conclusion is:

> **All 11 workstreams have implementation or evaluation infrastructure. Ten product capabilities are implemented within documented boundaries. Independent external proof for point 11 is still evaluator-controlled. Truecell does not claim universal 100% extraction accuracy.**

## Evidence by requested capability

### 1. Universal document intake

**Decision: implemented for the declared contract.**

- `truecell/router.py` accepts PDF, PNG, JPG/JPEG, TIFF, BMP and WebP, applies EXIF orientation to images, supports multi-frame images, rejects encrypted/corrupt/unsupported inputs and enforces page, frame, per-frame decoded-pixel and cumulative decoded-pixel limits before copying image data.
- `truecell/api.py` validates the same extensions, caps uploads and exposes the configured limits through `/api/health`.
- `tests/test_inputs_recovery.py` covers the 200-page boundary, multipage TIFF, compressed oversized images, cumulative frame preflight, encrypted/corrupt files, blank pages and page-local failure continuation.

**Boundary:** this is broad input acceptance, not universal document understanding. Unsupported container types must be converted first; scan-language OCR depends on a matching installed engine/language pack.

### 2. Automatic page analysis

**Decision: implemented.**

- `truecell/profiling.py` records content mode, native-text health, word/character counts, image coverage, ink, blur, contrast, skew, rotation, perspective risk, table likelihood/count, content cues, scripts, requested languages, risks and a recommended strategy.
- `truecell/pipeline.py` stores the profile, routing decision, planned candidates, execution mode, attempts and selected candidate in each page report.
- `truecell/export.py` exposes these records in Page Audit.
- `tests/test_page_profiling.py` verifies native/scanned routing, damaged-native OCR escalation, language metadata, checkpoint round trips and bounded candidate execution.

**Boundary:** profiling signals choose work and expose risk; they do not certify that a page was interpreted correctly.

### 3. Multiple extraction engines

**Decision: implemented, with optional engines disclosed accurately.**

- Native PDF extraction has independent line, text and word strategies.
- `truecell/ocr.py` supports local Tesseract and bundled checksum-verified RapidOCR, ranks language coverage and exposes a validated adapter registry for other local layout-aware engines.
- `truecell/pipeline.py` can run independent parallel-safe candidates in bounded two-worker batches, preserves deterministic plan order and records candidate IDs, phases, execution mode, scores, ranks and selection reasons.
- `tests/test_page_profiling.py` verifies parallel native and OCR candidates, deterministic selection, adapter output validation and honest capability reporting.

**Boundary:** PaddleOCR is not claimed as active merely because its package is detectable. It remains unavailable until the runtime and a Truecell adapter are explicitly installed and registered. Optional cloud extraction requires explicit configuration and opt-in and is outside the offline baseline.

### 4. Advanced table reconstruction

**Decision: implemented conservatively.**

- `truecell/table.py`, `truecell/layout.py` and `truecell/anchors.py` normalize wide/ragged tables, multi-line and multi-level headers, wrapped records, titles and header consensus.
- `truecell/ocr.py` reconstructs ruled-grid topology and explicit horizontal/vertical merged components from separator evidence.
- `truecell/stitch.py` joins compatible continuations, removes repeated headers, retains page receipts, merges split rows and keeps unrelated tables separate.
- `tests/test_tables.py`, `tests/test_ocr.py` and `tests/test_borderless_recovery.py` cover merged header paths, OCR and native vertical spans, horizontal body merges, empty columns, split rows, hierarchical section rows and conservative unruled gaps.

**Boundary:** source-backed spans are reconstructed; ambiguous unruled inheritance remains blank or becomes a review finding. Arbitrary nested tables and irregular multi-axis merge patterns can still require manual review.

### 5. Semantic understanding

**Decision: implemented as conservative inference.**

- `truecell/semantics.py` combines header signals and recurring value patterns to infer phone, date, ID, amount, quantity, total, balance and text roles.
- Repeated-page header consensus can restore a damaged reading only while retaining source evidence.
- `tests/test_semantics_validation.py` covers role inference, Hindi/Telugu header signals and the rule that semantics never rewrite values.
- `tests/test_multilingual_evidence.py` uses real Unicode Hindi and Telugu fixture text to verify script detection, JSON round trips, semantic roles and Excel preservation.

**Boundary:** this is document-local, rule-based evidence, not unrestricted natural-language understanding. Unknown or ambiguous headers remain conservative.

### 6. Strong validation

**Decision: implemented.**

- `truecell/validate.py` checks inconsistent shape, required/high-risk blanks, semantic mismatches, suspected shifts, sequence gaps, page continuity, provenance counts, date/number consistency, totals and discovered arithmetic.
- `truecell/constraints.py` learns sufficiently supported row equations and running-balance relations, records exact violations and creates counterfactual proposals.
- Export code protects formula-like strings and preserves identifiers such as leading-zero values.
- Regression evidence lives in `tests/test_validation.py`, `tests/test_semantics_validation.py`, `tests/test_baseline.py` and `tests/test_export_edge_cases.py`.

**Boundary:** arithmetic agreement can reveal inconsistencies but cannot prove the source is correct. Proposed changes are never applied automatically.

### 7. Evidence for every cell

**Decision: implemented for the displayed extraction.**

- `truecell/review.py` returns a deterministic evidence envelope for every displayed header/data cell: evidence ID, current and original value, original reading, exact source records, alternative readings, confidence meaning, location state and correction history.
- Non-empty cells satisfy an explicit invariant: exact source box or page-only/unlocated reason. Empty cells are explicitly `not_applicable` rather than assigned invented evidence.
- `truecell/api.py` serves the envelope through `/evidence`; `frontend/src/App.tsx` renders it in the source inspector.
- `truecell/export.py` links workbook data cells to Cell Evidence and includes Page Audit, Join Receipt, Provenance, Verification and Correction History.
- `tests/test_evidence_review.py` and `tests/test_multilingual_evidence.py` verify the shared evidence ID, source boxes, alternative readings, confidence semantics and edit history.

**Boundary:** an evidence link explains where a value came from. It does not make an OCR reading correct; missing exact geometry is surfaced for review.

### 8. Honest result states

**Decision: implemented.**

- Workspace lifecycle states are `ready`, `queued`, `processing`, `complete`, `partial` and `failed` in `truecell/workspace.py` and `truecell/api.py`.
- User-facing quality states are `needs_review`, `needs_rescan` and `reviewed` in `truecell/review.py`.
- A failed page creates a page error/finding while successful later pages remain available. An empty/no-table result cannot pass the Reviewed gate.
- `tests/test_workspace_qa.py`, `tests/test_inputs_recovery.py`, `tests/test_evidence_review.py` and `tests/test_api.py` cover interrupted work, partial results, failures and quality gates.

**Boundary:** `complete` is a processing-state assertion. Only the separate evidence/review gate can label the exact snapshot `reviewed`.

### 9. Exception-only human review

**Decision: implemented.**

- `truecell/review.py` builds a complete queue from validation findings, unlocated evidence and low-confidence OCR readings, with pagination and pending/checked counts.
- Each item is source-addressable where possible and must be checked individually. Completing the review also requires a source-check attestation and note.
- Edits require a reason, append a hash-chained history record and invalidate prior review. The review fingerprint binds source, values, evidence, findings and history.
- `truecell/api.py` exposes review, item-review, preview, revalidation and edit operations. The frontend presents the same workflow.
- `tests/test_evidence_review.py` verifies pagination, per-item acknowledgement, stale/tampered-state rejection, review invalidation and the Reviewed Excel gate.

**Boundary:** the system reduces review to exceptions; it does not remove human responsibility for ambiguous or high-risk evidence.

### 10. Reliable delivery

**Decision: implemented and locally verified.**

- Windows: `BUILD_PORTABLE.cmd`, `scripts/build_portable.py`, `portable/launcher.py` and `scripts/smoke_portable.py` support a Python-free one-folder build and exercise health, UI, extraction, export and persistence.
- Server/container: `Dockerfile`, `docker-compose.yml` and `scripts/smoke_server.py` cover the local API/UI, sample extraction, Excel/CSV/JSON downloads and persistence after restart.
- Recovery: `truecell/checkpoint.py`, `truecell/pipeline.py` and `truecell/workspace.py` bind checkpoints and saved results to source/code/options, continue after page failures, use atomic JSON writes and preserve immutable baselines.
- Delivery formats: Excel, CSV, audit JSON and local API responses are implemented in `truecell/export.py` and `truecell/api.py`.
- The CI workflow exercises the supported Python/OS matrix, frontend checks and container build/smoke path.

The final local gate rebuilt both delivery paths. Docker passed native and actual OCR extraction, exports, non-root/language-pack checks and restart persistence. The Windows EXE passed the same core workflow from a path containing spaces and restored saved work after restart. The ZIP is 152.53 MiB with SHA-256 `e786bec9bb3fa46d316c964552c82b47f56cf999af38800ae9bb4f65df50b3ea`.

**Boundary:** portable ZIPs and container images are derived artifacts. Rebuild and smoke-test them again after any functional source change; the ZIP remains a local release artifact and is not committed to Git.

### 11. Real external evaluation

**Decision: protocol and tooling complete; independent evidence pending.**

- `eval/benchmark.py` implements two distinct stages. Extraction validates the version-1 manifest and source hashes, runs without truth, records the extractor source fingerprint/revision, writes version-2 `run.json`, and hashes each saved audit and workbook. Scoring later consumes those saved artifacts without re-extraction.
- The evaluator must preserve the printed SHA-256 of `run.json` outside the output folder. Scoring requires that seal and rejects a missing or changed seal, changed source fingerprint, mismatched case set, changed manifest/audit/workbook, unsafe path, source mismatch, changed OCR-language route or a run that does not state truth was withheld.
- Each case carries a runtime signature over its source, extraction code and options, installed OCR packages, bundled ONNX assets, Tesseract version, requested installed language assets and OCR-language route.
- Scoring verifies every saved workbook `Data N` cell against a fresh export from the frozen audit, including value, type and number format, before comparing the withheld truth.
- `tests/test_blind_benchmark.py` covers unsafe manifests, the external run seal, source and runtime fingerprints, workbook/audit tampering, manifest changes, saved-result scoring and a two-stage integration case in which truth is introduced only after extraction.
- `docs/BLIND_EVALUATION.md` and `eval/blind_manifest.example.json` provide the evaluator procedure and distinguish manifest schema version 1 from run-metadata schema version 2.

**Boundary:** the repository’s synthetic, sample and public regression documents were visible during development and are not independent blind evidence. The protocol and tamper checks are implemented, but no actual independent evaluator result exists yet. Completion of the final proof requires an outside evaluator to provide unseen authorized files and withheld truth, preserve the external run seal, and publish the frozen manifest, run metadata and result hashes.

## Success-standard cross-check

| Success standard | Audit finding |
|---|---|
| Maximum automation on difficult documents | Automatic profiling, multiple candidates, recovery strategies, complex-table reconstruction and page continuation are implemented. |
| Immediate warning when uncertain | Candidate disagreements, page errors, low confidence, missing evidence and validation findings feed explicit quality and review states. |
| No silent corruption | Source/value fingerprints, immutable baselines, append-only correction history, validation findings and quality-gated reviewed export reduce silent changes; universal prevention cannot be guaranteed. |
| Every value traceable | Every non-empty displayed cell is either source-box located or explicitly page-only/unlocated; empty cells are marked not applicable. |
| Failures recoverable | Verified checkpoints, page-local continuation, partial workspaces, retries and persistent local state are implemented. |
| Only problematic cells need attention | The review queue prioritizes findings, missing locations and low-confidence cells, while retaining access to the full source for final attestation. |

## Final release gate

Local gate completed on 22 October 2026:

- 304 Python tests, Ruff lint/format and dependency consistency passed.
- 16 frontend tests and the TypeScript/Vite production build passed.
- 23/23 development cases and strict audit/workbook/source verification passed.
- 5/5 RapidOCR-only scan cases and all four disclosed public checks passed.
- Docker and Windows portable extraction/export/restart smoke tests passed.
- Secret/personal-file and required-file checks are run again immediately before commit.

Before calling a specific commit release-ready, run and retain the results of:

1. Full Python tests and Ruff checks.
2. Frontend unit tests and production build, including a clean generated `frontend/dist` check.
3. Exact recorded-output verification against source hashes and truth files.
4. Docker build, server smoke test and persistence-after-restart check.
5. Windows portable rebuild and portable smoke test from a path containing spaces.
6. Secret/personal-file scan, required-file audit and clean Git status.
7. Push the exact verified commit and confirm all required GitHub checks pass.

For every release, push the exact verified source and confirm the required GitHub checks. These checks establish that the engineering artifact matches this audit. They do not convert finite fixture results into a universal accuracy guarantee or replace the independent evaluation required by point 11.
