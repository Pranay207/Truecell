import type { Cell, Issue, Result, SourceRecord } from "./types.ts";

export function active(status: string): boolean {
  return ["ready", "processing", "queued"].includes(status);
}
export function issueCell(result: Result, issue: Issue): Cell | null {
  const candidateTables = issue.table
    ? [issue.table - 1]
    : result.tables.map((_, i) => i);
  for (const table of candidateTables) {
    const target = result.tables[table];
    if (!target) continue;
    const row = target.provenance.findIndex((sources) =>
      sources.some(
        ([page, row]) =>
          page === issue.page && (issue.row == null || row === issue.row),
      ),
    );
    if (row >= 0)
      return {
        table,
        row,
        column: Math.min(
          Math.max(0, (issue.column ?? 1) - 1),
          Math.max(0, target.rows[row].length - 1),
        ),
      };
  }
  return null;
}
export function recordsFor(result: Result, cell: Cell): SourceRecord[] {
  const table = result.tables[cell.table];
  if (!table) return [];
  return cell.row === -1
    ? (table.header_sources[cell.column] ?? [])
    : (table.cell_sources[cell.row]?.[cell.column] ?? []);
}
export function cellValue(result: Result, cell: Cell): string {
  const table = result.tables[cell.table];
  if (!table) return "";
  return cell.row === -1
    ? (table.headers[cell.column] ?? "")
    : (table.rows[cell.row]?.[cell.column] ?? "");
}
export function countRows(result?: Result): number {
  return result?.tables.reduce((n, t) => n + t.rows.length, 0) ?? 0;
}
export type FilteredRow = {
  rowIndex: number;
  row: string[];
};
export function filterRows(
  headers: string[],
  rows: string[][],
  query: string,
): FilteredRow[] {
  const needle = query.trim().toLocaleLowerCase();
  return rows.flatMap((row, rowIndex) => {
    const matches =
      needle.length === 0 ||
      headers.some((header) =>
        header.toLocaleLowerCase().includes(needle),
      ) ||
      row.some((value) => value.toLocaleLowerCase().includes(needle));
    return matches ? [{ rowIndex, row }] : [];
  });
}
export function labelStatus(status: string): string {
  return (
    (
      {
        complete: "Extracted",
        partial: "Needs another pass",
        failed: "Processing stopped",
        ready: "Preparing",
        processing: "Extracting",
        queued: "Queued",
      } as Record<string, string>
    )[status] ?? status
  );
}
