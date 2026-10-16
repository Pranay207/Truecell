export type SourceRecord = {
  page: number;
  bbox?: number[] | null;
  text?: string;
  engine?: string;
  confidence?: number | null;
  role?: string;
  initial_reading?: string;
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
  options?: { verify?: boolean; force_ocr?: boolean; force?: boolean };
  result_is_previous?: boolean;
  forked_from?: string;
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
