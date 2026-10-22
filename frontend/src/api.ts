import type {
  Cell,
  CellEvidence,
  ChallengeReport,
  Job,
  PreviewReport,
  Result,
  ReviewQueue,
  Sample,
} from "./types";

const ROOT = "/api";
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${ROOT}${path}`, init);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      /* Keep the HTTP error when a proxy returns HTML. */
    }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}
const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export const api = {
  health: () => request<{ status: string }>("/health"),
  jobs: () => request<{ jobs: Job[] }>("/jobs"),
  samples: () => request<{ samples: Sample[] }>("/samples"),
  sample: (filename: string) =>
    request<Job>(`/samples/${encodeURIComponent(filename)}`, {
      method: "POST",
    }),
  upload: (file: File, verify: boolean, force: boolean, ocrLanguages = "eng") => {
    const body = new FormData();
    body.append("file", file);
    body.append("verify", String(verify));
    body.append("force_ocr", String(force));
    body.append("ocr_languages", ocrLanguages);
    return request<Job>("/jobs", { method: "POST", body });
  },
  job: (id: string, signal?: AbortSignal) =>
    request<Job>(`/jobs/${id}`, { signal }),
  remove: (id: string, confirmation: string) =>
    request<{ deleted: string; name: string }>(
      `/jobs/${id}`,
      json({ confirmation }, "DELETE"),
    ),
  process: (
    id: string,
    options: { verify: boolean; force_ocr: boolean; ocr_languages?: string },
  ) =>
    request<Job>(`/jobs/${id}/process`, json(options)),
  result: (id: string) =>
    request<{
      result: Result;
      fingerprint: string;
      coverage: Record<string, number>;
    }>(`/jobs/${id}/result`),
  edit: (
    id: string,
    cell: Cell,
    value: string,
    note: string,
    fingerprint?: string,
  ) =>
    request<Job>(
      `/jobs/${id}/cells`,
      json({ ...cell, value, note, fingerprint }, "PATCH"),
    ),
  review: (id: string, note: string, fingerprint?: string) =>
    request<Job>(
      `/jobs/${id}/review`,
      json({ source_checked: true, note, fingerprint }),
    ),
  reviewItem: (
    id: string,
    itemId: string,
    sourceChecked: boolean,
    fingerprint?: string,
  ) =>
    request<Job>(
      `/jobs/${id}/review-items`,
      json({ item_id: itemId, source_checked: sourceChecked, fingerprint }),
    ),
  reviewQueue: (
    id: string,
    offset = 0,
    limit = 100,
    table?: number,
    status?: "pending" | "checked",
  ) => {
    const query = new URLSearchParams({
      offset: String(offset),
      limit: String(limit),
    });
    if (table != null) query.set("table", String(table));
    if (status) query.set("status", status);
    return request<ReviewQueue>(`/jobs/${id}/review-queue?${query}`);
  },
  evidence: (id: string, cell: Cell, fingerprint?: string) => {
    const query = new URLSearchParams({
      table: String(cell.table),
      row: String(cell.row),
      column: String(cell.column),
    });
    if (fingerprint) query.set("fingerprint", fingerprint);
    return request<CellEvidence>(`/jobs/${id}/evidence?${query}`);
  },
  preview: (id: string, cell: Cell, value: string, fingerprint?: string) =>
    request<PreviewReport>(
      `/jobs/${id}/preview`,
      json({ ...cell, value, fingerprint }),
    ),
  challenge: (id: string, table: number, fingerprint?: string) =>
    request<ChallengeReport>(
      `/jobs/${id}/challenge`,
      json({ table, fingerprint }),
    ),
  pageInfo: (id: string, page: number, signal?: AbortSignal) =>
    request<{ width: number; height: number }>(
      `/jobs/${id}/pages/${page}/info`,
      { signal },
    ),
  image: (id: string, page: number) => `${ROOT}/jobs/${id}/pages/${page}/image`,
  download: (
    id: string,
    kind:
      | "export.xlsx"
      | "reviewed.xlsx"
      | "audit.json"
      | "baseline.json"
      | "source",
  ) => `${ROOT}/jobs/${id}/${kind}`,
  csv: (id: string, table: number) =>
    `${ROOT}/jobs/${id}/export.csv?table=${table + 1}`,
};
