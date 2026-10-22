export type SourceRecord = {
  page: number;
  bbox?: number[] | null;
  text?: string;
  engine?: string;
  confidence?: number | null;
  role?: string;
  initial_reading?: string;
  confidence_evidence?: RecognitionConfidence;
};
export type RecognitionConfidence = {
  kind: "ocr_score" | "engine_score" | "native_text" | "not_reported";
  score: number | null;
  label: string;
  engine: string;
  meaning: string;
};
export type CellEvidence = {
  evidence_id: string;
  cell: Cell & { kind: "header" | "data" };
  value: string;
  original_value: string;
  original_reading: string;
  sources: SourceRecord[];
  alternative_readings: {
    text: string;
    kind: string;
    engine: string;
    page?: number | null;
    bbox?: number[] | null;
    confidence: RecognitionConfidence;
  }[];
  confidence: RecognitionConfidence;
  location: {
    status: "located" | "unlocated" | "not_applicable";
    evidence_state: "exact_source_box" | "page_only_review" | "empty_cell";
    located: boolean;
    reason: string;
    page?: number | null;
    source_records: number;
    located_records: number;
  };
  correction_history: Record<string, unknown>[];
  correction_count: number;
};
export type Table = {
  headers: string[];
  rows: string[][];
  page: number;
  engine: string;
  confidence: number;
  provenance: [number, number][][];
  cell_sources: SourceRecord[][][];
  header_sources: SourceRecord[][];
  notes: string[];
  page_summaries?: Record<string, unknown>[];
  join_receipt?: {
    pages: number[];
    page_joins: number;
    repeated_headers_removed: number;
    split_rows_recovered: number;
    rows_by_page: { page: number; rows: number }[];
    output_rows: number;
  };
};
export type Issue = {
  severity: string;
  page: number;
  row?: number | null;
  column?: number | null;
  reason: string;
  suggestion?: string;
  code: string;
  table?: number | null;
};
export type Attempt = {
  engine: string;
  strategy: string;
  selected: boolean;
  tables: number;
  cells: number;
  seconds: number;
  error: string;
};
export type PageReport = {
  page: number;
  route: string;
  engine: string;
  seconds: number;
  error: string;
  attempts: Attempt[];
  profile?: {
    requested_ocr_languages?: string[];
    ocr_engine_language_coverage?: Record<string, string[]>;
    missing_ocr_languages?: string[];
    [key: string]: unknown;
  };
};
export type Relation = {
  table: number;
  formula: string;
  matched: number;
  checked: number;
  violations: {
    row: number;
    column: number;
    observed: string;
    expected: string;
  }[];
};
export type Proposal = {
  table: number;
  row: number;
  column: number;
  observed: string;
  proposed: string;
  support_count: number;
  supporting_equations: string[];
  basis: string;
};
export type Result = {
  source: string;
  source_sha256: string;
  tables: Table[];
  issues: Issue[];
  pages: PageReport[];
  seconds: number;
  constraints: Relation[];
  proposals: Proposal[];
  review: { status?: string; fingerprint?: string; note?: string };
  history: Record<string, unknown>[];
};
export type ReviewQueueItem = {
  id: string;
  kind: "finding" | "confidence" | "evidence";
  severity: string;
  page: number;
  title: string;
  reason: string;
  suggestion: string;
  table?: number | null;
  row?: number | null;
  column?: number | null;
  confidence?: number | null;
  status: "pending" | "checked";
  checked_at?: string | null;
};
export type ReviewQueue = {
  items: ReviewQueueItem[];
  total: number;
  visible: number;
  pending: number;
  checked: number;
  filtered_total: number;
  filtered_pending: number;
  offset: number;
  limit: number | null;
  remaining: number;
  has_more: boolean;
  next_offset?: number | null;
  omitted: number;
  confidence_threshold: number;
};
export type Job = {
  id: string;
  name: string;
  status: string;
  created?: string;
  progress?: number;
  progress_page?: number;
  progress_pages?: number;
  error?: string;
  result?: Result;
  fingerprint?: string;
  coverage?: Record<string, number>;
  options?: {
    verify?: boolean;
    force_ocr?: boolean;
    force?: boolean;
    ocr_languages?: string;
  };
  result_is_previous?: boolean;
  forked_from?: string;
  review_queue?: ReviewQueue;
  evidence_coverage?: {
    nonempty_cells: number;
    located: number;
    unlocated: number;
    coverage: number;
    complete: boolean;
  };
  quality?: {
    status: "needs_review" | "needs_rescan" | "reviewed";
    reasons: string[];
    reviewed_export_ready: boolean;
    draft_export_ready: boolean;
  };
  reviewed?: boolean;
};
export type Sample = { filename: string; name: string; pages?: number };
export type Cell = { table: number; row: number; column: number };
export type PreviewReport = {
  observed: string;
  proposed: string;
  before: { findings: number; failed_equation_checks: number };
  after: { findings: number; failed_equation_checks: number };
  fingerprint: string;
  saved: false;
};
export type ChallengeCase = {
  row: number;
  column: number;
  original: string;
  mutated: string;
  caught: boolean;
  new_findings: string[];
};
export type ChallengeReport = {
  caught: number;
  tested: number;
  unmodeled_columns: number[];
  cases: ChallengeCase[];
  scope: string;
  baseline_sha256: string;
  fingerprint: string;
  saved: false;
  row_limit: number;
  rows_available: number;
  rows_tested: number;
};
