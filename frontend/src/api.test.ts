import { strict as assert } from "node:assert";
import { test } from "node:test";
import { api, ApiError } from "./api.ts";

test("upload sends explicit OCR languages with the extraction profile", async () => {
  const previous = globalThis.fetch;
  let body: FormData | undefined;
  globalThis.fetch = async (_input, init) => {
    body = init?.body as FormData;
    return new Response(JSON.stringify({ id: "dummy", status: "processing" }), {
      status: 200,
    });
  };
  try {
    const file = new File(["%PDF"], "dummy.pdf", { type: "application/pdf" });
    await api.upload(file, true, false, "eng+tel");
    assert.equal(body?.get("verify"), "true");
    assert.equal(body?.get("force_ocr"), "false");
    assert.equal(body?.get("ocr_languages"), "eng+tel");
  } finally {
    globalThis.fetch = previous;
  }
});

test("counterfactual preview sends the exact snapshot and preserves numeric text", async () => {
  const previous = globalThis.fetch;
  let requested: { url: string; method?: string; body: unknown } | undefined;
  globalThis.fetch = async (input, init) => {
    requested = {
      url: String(input),
      method: init?.method,
      body: JSON.parse(String(init?.body)),
    };
    return new Response(
      JSON.stringify({
        before: { findings: 2, failed_equation_checks: 2 },
        after: { findings: 0, failed_equation_checks: 0 },
        saved: false,
      }),
      { status: 200 },
    );
  };
  try {
    const preview = await api.preview(
      "dummy",
      { table: 0, row: 10, column: 5 },
      "001.20",
      "snapshot",
    );
    assert.deepEqual(requested, {
      url: "/api/jobs/dummy/preview",
      method: "POST",
      body: {
        table: 0,
        row: 10,
        column: 5,
        value: "001.20",
        fingerprint: "snapshot",
      },
    });
    assert.equal(preview.saved, false);
    assert.equal(preview.after.failed_equation_checks, 0);
  } finally {
    globalThis.fetch = previous;
  }
});

test("challenge uses zero-based table index and keeps missed injections visible", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "/api/jobs/dummy/challenge");
    assert.deepEqual(JSON.parse(String(init?.body)), {
      table: 1,
      fingerprint: "snapshot",
    });
    return new Response(
      JSON.stringify({
        caught: 0,
        tested: 1,
        saved: false,
        cases: [
          {
            row: 1,
            column: 2,
            original: "12",
            mutated: "19.13",
            caught: false,
          },
        ],
      }),
      { status: 200 },
    );
  };
  try {
    const result = await api.challenge("dummy", 1, "snapshot");
    assert.equal(result.caught, 0);
    assert.equal(result.cases[0].caught, false);
  } finally {
    globalThis.fetch = previous;
  }
});

test("priority review records the exact queue item and source-check state", async () => {
  const previous = globalThis.fetch;
  let requested: { url: string; method?: string; body: unknown } | undefined;
  globalThis.fetch = async (input, init) => {
    requested = {
      url: String(input),
      method: init?.method,
      body: JSON.parse(String(init?.body)),
    };
    return new Response(JSON.stringify({ id: "dummy", status: "complete" }), {
      status: 200,
    });
  };
  try {
    await api.reviewItem("dummy", "confidence-0-1-2", true, "snapshot");
    assert.deepEqual(requested, {
      url: "/api/jobs/dummy/review-items",
      method: "POST",
      body: {
        item_id: "confidence-0-1-2",
        source_checked: true,
        fingerprint: "snapshot",
      },
    });
  } finally {
    globalThis.fetch = previous;
  }
});

test("recovery accepts a new workspace ID while retaining the fork origin", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "/api/jobs/original/process");
    assert.deepEqual(JSON.parse(String(init?.body)), {
      verify: true,
      force_ocr: false,
    });
    return new Response(
      JSON.stringify({
        id: "new-workspace",
        forked_from: "original",
        status: "processing",
      }),
      { status: 200 },
    );
  };
  try {
    const resumed = await api.process("original", {
      verify: true,
      force_ocr: false,
    });
    assert.equal(resumed.id, "new-workspace");
    assert.equal(resumed.forked_from, "original");
  } finally {
    globalThis.fetch = previous;
  }
});

test("stale snapshot errors remain actionable instead of being treated as a result", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: "The workspace changed. Reload it before saving this change.",
      }),
      { status: 409 },
    );
  try {
    await assert.rejects(
      api.preview("dummy", { table: 0, row: 0, column: 0 }, "12", "old"),
      (error: unknown) =>
        error instanceof ApiError &&
        error.status === 409 &&
        error.message.includes("Reload"),
    );
  } finally {
    globalThis.fetch = previous;
  }
});

test("result endpoint preserves the API response envelope", async () => {
  const previous = globalThis.fetch;
  let requested = "";
  globalThis.fetch = async (input) => {
    requested = String(input);
    return new Response(
      JSON.stringify({
        result: { source: "dummy.pdf" },
        fingerprint: "snapshot",
        coverage: { modeled_columns: 4 },
      }),
      { status: 200 },
    );
  };
  try {
    const response = await api.result("dummy");
    assert.equal(requested, "/api/jobs/dummy/result");
    assert.equal(response.result.source, "dummy.pdf");
    assert.equal(response.fingerprint, "snapshot");
    assert.deepEqual(response.coverage, { modeled_columns: 4 });
  } finally {
    globalThis.fetch = previous;
  }
});

test("workspace deletion sends the exact name as explicit confirmation", async () => {
  const previous = globalThis.fetch;
  let requested: { url: string; method?: string; body: unknown } | undefined;
  globalThis.fetch = async (input, init) => {
    requested = {
      url: String(input),
      method: init?.method,
      body: JSON.parse(String(init?.body)),
    };
    return new Response(
      JSON.stringify({ deleted: "workspace-id", name: "invoice.pdf" }),
      { status: 200 },
    );
  };
  try {
    const result = await api.remove("workspace-id", "invoice.pdf");
    assert.deepEqual(requested, {
      url: "/api/jobs/workspace-id",
      method: "DELETE",
      body: { confirmation: "invoice.pdf" },
    });
    assert.equal(result.deleted, "workspace-id");
    assert.equal(result.name, "invoice.pdf");
  } finally {
    globalThis.fetch = previous;
  }
});
