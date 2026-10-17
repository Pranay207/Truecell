import type { Table } from "./types";
import "./JoinReceipt.css";

export function JoinReceipt({ table }: { table: Table }) {
  const receipt = table.join_receipt;
  if (!receipt?.pages?.length) return null;

  const multiPage = receipt.pages.length > 1;
  const sourceRows = receipt.rows_by_page.reduce(
    (total, entry) => total + entry.rows,
    0,
  );

  return (
    <section className="join-receipt" aria-label="Table joining receipt">
      <div className="join-receipt-heading">
        <span className="join-receipt-mark" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <div>
          <span>JOIN RECEIPT</span>
          <strong>
            {multiPage
              ? `${receipt.pages.length} pages joined into one table`
              : "Single-page table — no join needed"}
          </strong>
        </div>
      </div>
      <dl>
        <div>
          <dt>Page joins</dt>
          <dd>{receipt.page_joins}</dd>
        </div>
        <div>
          <dt>Repeated headers removed</dt>
          <dd>{receipt.repeated_headers_removed}</dd>
        </div>
        <div>
          <dt>Split rows recovered</dt>
          <dd>{receipt.split_rows_recovered}</dd>
        </div>
      </dl>
      <p className="join-receipt-pages">
        <span>Rows read / page</span>
        {receipt.rows_by_page.map(({ page, rows }) => (
          <b key={page}>
            P{page} <i>{rows}</i>
          </b>
        ))}
        <em aria-label={`${sourceRows} source row fragments became ${receipt.output_rows} rows`}>
          {sourceRows} source → {receipt.output_rows} output
        </em>
      </p>
    </section>
  );
}
