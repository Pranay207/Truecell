import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  active,
  cellValue,
  countRows,
  filterRows,
  issueCell,
  recordsFor,
} from "./format.ts";
import type { Result } from "./types.ts";

const result: Result = {
  source: "dummy.pdf",
  source_sha256: "a",
  seconds: 1,
  pages: [],
  issues: [],
  constraints: [],
  proposals: [],
  review: { status: "unreviewed" },
  history: [],
  tables: [
    {
      headers: ["ID", "Amount"],
      rows: [
        ["001", "12"],
        ["002", "14"],
      ],
      page: 1,
      engine: "native",
      confidence: 1,
      notes: [],
      provenance: [
        [[1, 1]],
        [
          [1, 2],
          [2, 1],
        ],
      ],
      header_sources: [[], []],
      cell_sources: [
        [[], []],
        [[{ page: 2, bbox: [1, 2, 3, 4], text: "002", confidence: null }], []],
      ],
    },
  ],
};
test("findings follow actual multi-page provenance instead of displayed row arithmetic", () => {
  assert.deepEqual(
    issueCell(result, {
      severity: "error",
      page: 2,
      row: 1,
      column: 2,
      reason: "Dummy",
      code: "test",
      table: 1,
    }),
    { table: 0, row: 1, column: 1 },
  );
});
test("unlocated page findings do not point to an unrelated row", () => {
  assert.equal(
    issueCell(result, {
      severity: "error",
      page: 9,
      row: 1,
      column: 1,
      reason: "Dummy",
      code: "test",
    }),
    null,
  );
});
test("header selection and missing source geometry are safe", () => {
  assert.equal(cellValue(result, { table: 0, row: -1, column: 1 }), "Amount");
  assert.deepEqual(recordsFor(result, { table: 0, row: 0, column: 1 }), []);
  assert.deepEqual(
    recordsFor(result, { table: 0, row: 1, column: 0 })[0].bbox,
    [1, 2, 3, 4],
  );
});
test("row count and progress state use real extraction data", () => {
  assert.equal(countRows(result), 2);
  assert.equal(countRows(), 0);
  assert.equal(active("partial"), false);
  assert.equal(active("processing"), true);
});
test("table search preserves original row indices", () => {
  const rows = [
    ["Germany", "Berlin Institute", "Berlin"],
    ["France", "Sorbonne", "Paris"],
    ["Germany", "Hof University", "Hof"],
  ];

  assert.deepEqual(filterRows(["Country", "Name", "City"], rows, "hof"), [
    { rowIndex: 2, row: rows[2] },
  ]);
});
test("table search is case-insensitive across headers and values", () => {
  const headers = ["Country/Region", "Billing City"];
  const rows = [
    ["Germany", "KOLN"],
    ["India", "Hyderabad"],
  ];

  assert.deepEqual(filterRows(headers, rows, "gErMaNy"), [
    { rowIndex: 0, row: rows[0] },
  ]);
  assert.deepEqual(filterRows(headers, rows, "billing"), [
    { rowIndex: 0, row: rows[0] },
    { rowIndex: 1, row: rows[1] },
  ]);
});
test("blank table search returns every indexed row", () => {
  const rows = [["one"], ["two"]];

  assert.deepEqual(filterRows(["Value"], rows, "   "), [
    { rowIndex: 0, row: rows[0] },
    { rowIndex: 1, row: rows[1] },
  ]);
});
