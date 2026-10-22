# Truecell frontend

React + TypeScript interface for the local Truecell extraction engine. The Python server serves `dist/`; end users do not need Node for the prebuilt interface.

## Development

Use Node 22.12 or newer. Start the backend from the project root with `.venv\Scripts\python.exe run.py --port 8503 --no-browser` (or `.venv/bin/python run.py --port 8503 --no-browser` on Linux/macOS). In `frontend/`, run `npm ci`, then `npm run dev`. Vite listens on loopback and proxies `/api` to `http://127.0.0.1:8503`. Adjust that target in `vite.config.ts` if the backend uses another port.

- `npm run test`: provenance/navigation logic checks using Node's test runner.
- `npm run build`: strict TypeScript checks and an optimized static production build.
- `npm run preview`: inspect the built interface locally. Use the Python application for API calls.

No external fonts, image services, analytics or cloud AI are requested by this interface. Interface icons are implemented as inline SVG. Dependencies are credited in `package.json` and pinned by `package-lock.json`.

## REST contract

All routes are same-origin, rooted at `/api`; `src/api.ts` centralizes requests. Errors use an HTTP error status and `{ "detail": "human-readable explanation" }`.

| Route                               | Contract                                                                                                                                                  |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /health`                       | `{status}`                                                                                                                                                |
| `GET /jobs`                         | `{jobs: Job[]}`                                                                                                                                           |
| `POST /jobs`                        | Multipart `file`, `verify`, `force_ocr`, `ocr_languages`. Boolean fields are strings. Starts processing and returns a Job.                                |
| `GET /jobs/{id}`                    | Job metadata and progress; includes `result`, `fingerprint`, `coverage` once available. Polled while processing.                                          |
| `DELETE /jobs/{id}`                 | JSON `{confirmation}` containing the exact workspace filename. Removes an idle local workspace and returns `{deleted,name}`; active jobs return 409.      |
| `POST /jobs/{id}/process`           | JSON `{verify,force_ocr,ocr_languages}`. Resumes an untouched failed/partial job, or returns a new forked workspace when the existing job has edits/review. |
| `GET /jobs/{id}/result`             | Current extraction result with snapshot fingerprint.                                                                                                    |
| `PATCH /jobs/{id}/cells`            | JSON `{table,row,column,value,note,fingerprint}`; returns updated Job. Indices start at zero; row `-1` means header. Stale fingerprint should return 409. |
| `POST /jobs/{id}/review`            | JSON `{source_checked:true,note,fingerprint}`; returns updated Job.                                                                                       |
| `POST /jobs/{id}/revalidate`        | Re-runs validation on the current saved working result.                                                                                                  |
| `GET /jobs/{id}/evidence`           | Query `{table,row,column,fingerprint}`; returns source coverage for that exact current snapshot.                                                         |
| `POST /jobs/{id}/preview`           | Evaluates one proposed cell value on a disposable copy and returns before/after validation counts.                                                       |
| `POST /jobs/{id}/challenge`         | Runs bounded controlled mutations against the production validator without saving.                                                                      |
| `GET /jobs/{id}/pages/{page}/info`  | `{width,height}` in PDF points. Page starts at 1. Required for accurate source-box placement.                                                             |
| `GET /jobs/{id}/pages/{page}/image` | PNG image of original source page.                                                                                                                        |
| `GET /jobs/{id}/source`             | Original uploaded document.                                                                                                                               |
| `GET /jobs/{id}/export.xlsx`        | Current Excel with evidence and validation.                                                                                                               |
| `GET /jobs/{id}/export.csv`         | Current table as CSV; use the table query when selecting among multiple extracted tables.                                                                 |
| `GET /jobs/{id}/audit.json`         | Current complete audit JSON.                                                                                                                              |
| `GET /jobs/{id}/baseline.json`      | Immutable original extraction JSON.                                                                                                                       |
| `GET /samples`                      | `{samples:[{filename,name,pages?}]}`; public/dummy examples only.                                                                                         |
| `POST /samples/{filename}`          | Starts extraction and returns a Job.                                                                                                                      |

Job fields: `id`, `name`, `status`, optional `created`, `error`, `message`, `forked_from`, `progress` (0–1), `progress_page`, `progress_pages`, `result`, `fingerprint`, `coverage`. Statuses: `ready`, `queued`, `processing`, `complete`, `partial`, `failed`.

`result` is the engine's `Result.to_dict()` payload. The client uses `provenance` to locate findings and `cell_sources` / `header_sources` for source evidence. Values render as React text; document content is never inserted as HTML. No displayed confidence score is described as measured accuracy.

## Review behavior

Corrections require an explicit source-check checkbox and a reason. Changing the selected cell, source document or snapshot resets that form. Recording a source check requires its own attestation and note; edits invalidate the prior check. Proposals populate a draft field only and never silently mutate data. The original readings and baseline remain available.

Missing source previews leave result/export controls usable. No-table results retain findings, the engine audit and exports. Frontend file validation is convenience only; the server must enforce file type, size, page count, path safety and mutation validation.

## Validation tools and recovery

- `POST /jobs/{id}/preview`: JSON `{table,row,column,value,fingerprint}`. Returns `{observed,proposed,before:{findings,failed_equation_checks},after:{findings,failed_equation_checks},fingerprint,saved:false}`. This changes only a disposable copy.
- `POST /jobs/{id}/challenge`: JSON `{table,fingerprint}`. Returns the real validator-sensitivity report, including caught/tested, unmodeled columns, injection cases, tested/available row counts and `saved:false`. It uses at most 24 edits on the first 120 rows. This is not an OCR accuracy measurement.
- `POST /jobs/{id}/process`: JSON `{verify,force_ocr,ocr_languages}`. Reuses verified checkpoints for untouched jobs. Edited/reviewed copies fork into a new job with `forked_from`, preserving the original workspace. The returned ID can differ from the requested ID.

The Challenge panel and preview receipts never apply edits. Pending source checks, preview/challenge reports and correction drafts are bound to the current job/snapshot/target. The Audit panel displays recent correction history; its complete record is included in the audit JSON.
