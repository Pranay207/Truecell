"""Exercise a running Truecell API and its persistent workspace end to end."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def request(url: str, *, data: bytes | None = None, timeout: float = 30) -> bytes:
    headers = {"Content-Type": "application/json"} if data is not None else {}
    operation = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(operation, timeout=timeout) as response:
        if response.status not in {200, 202}:
            raise RuntimeError(f"Unexpected HTTP {response.status}: {url}")
        return response.read()


def json_request(url: str, *, data: bytes | None = None) -> dict:
    return json.loads(request(url, data=data))


def wait_for_health(base: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last_error = "server did not respond"
    while time.monotonic() < deadline:
        try:
            health = json_request(base + "/api/health")
            if health.get("status") == "ok":
                return health
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Server health check timed out: {last_error}")


def wait_for_job(base: str, identifier: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = json_request(base + f"/api/jobs/{identifier}")
        if job["status"] in {"complete", "partial", "failed"}:
            if job["status"] != "complete":
                raise RuntimeError(
                    f"Server extraction ended as {job['status']}: {job.get('error')}"
                )
            return job
        time.sleep(0.5)
    raise RuntimeError(f"Server extraction timed out: {identifier}")


def verify_saved_workspace(base: str, state_file: Path) -> None:
    state = json.loads(state_file.read_text(encoding="utf-8"))
    saved = json_request(base + "/api/jobs")["jobs"]
    saved_ids = {job["id"] for job in saved}
    if state["job_id"] not in saved_ids:
        raise AssertionError("Saved workspace was not restored after restart.")
    restored = json_request(base + f"/api/jobs/{state['job_id']}")
    if restored.get("status") != "complete" or restored.get("quality") == "needs_rescan":
        raise AssertionError("Saved workspace metadata survived but its completed result did not.")
    result = restored.get("result") or {}
    if result.get("source_sha256") != state.get("source_sha256"):
        raise AssertionError("Restored workspace is not bound to the original source.")
    if result.get("tables") != state.get("tables"):
        raise AssertionError("Restored workspace table content changed after restart.")
    audit = json.loads(request(base + f"/api/jobs/{state['job_id']}/audit.json"))
    if audit.get("source_sha256") != state.get("source_sha256"):
        raise AssertionError("Restored audit is unavailable or source-mismatched.")


def verify_extraction(
    base: str,
    sample: str,
    timeout: float,
    state_file: Path | None,
    *,
    require_ocr: bool = False,
) -> None:
    encoded = urllib.parse.quote(sample + ".pdf")
    created = json_request(base + f"/api/samples/{encoded}", data=b"{}")
    job = wait_for_job(base, created["id"], timeout)
    actual = job["result"]["tables"]
    truth_path = ROOT / "samples" / f"{sample}.truth.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))["tables"]
    if len(actual) != len(truth):
        raise AssertionError(f"Expected {len(truth)} tables, received {len(actual)}.")
    for observed, expected in zip(actual, truth, strict=True):
        if observed["headers"] != expected["headers"] or observed["rows"] != expected["rows"]:
            raise AssertionError(f"Extraction mismatch for {sample}.")
    if require_ocr:
        pages = job["result"].get("pages", [])
        if not pages or not all(
            page.get("route") == "ocr"
            and page.get("engine") in {"rapidocr", "tesseract", "tesseract-cell"}
            for page in pages
        ):
            raise AssertionError("Scanned smoke case did not exercise a bundled OCR engine.")

    workbook = request(base + f"/api/jobs/{created['id']}/export.xlsx")
    if not workbook.startswith(b"PK") or len(workbook) <= 5_000:
        raise AssertionError("Excel download is missing or invalid.")
    csv_output = request(base + f"/api/jobs/{created['id']}/export.csv")
    if not csv_output.strip():
        raise AssertionError("CSV download is empty.")
    audit = json.loads(request(base + f"/api/jobs/{created['id']}/audit.json"))
    if not audit.get("tables"):
        raise AssertionError("Audit download contains no tables.")
    if state_file is not None:
        state_file.write_text(
            json.dumps(
                {
                    "job_id": created["id"],
                    "source_sha256": job["result"].get("source_sha256"),
                    "tables": actual,
                }
            ),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8501")
    parser.add_argument("--sample", default="A_invoice_register")
    parser.add_argument("--ocr-sample", default="C_scanned_inventory")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--verify-state-only", action="store_true")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    health = wait_for_health(base, args.timeout)
    if health.get("offline") is not True:
        raise AssertionError("Container is not reporting offline/local processing.")
    if not {"eng", "hin", "tel"}.issubset(health.get("tesseract_languages", [])):
        raise AssertionError("Container is missing a required bundled Tesseract language pack.")
    if not {"rapidocr", "tesseract"}.issubset(health.get("ocr_engines", [])):
        raise AssertionError("Container is missing a required bundled OCR engine.")
    if b'<div id="root"></div>' not in request(base + "/"):
        raise AssertionError("React application shell is unavailable.")

    if args.verify_state_only:
        verify_saved_workspace(base, args.state_file)
        print("PASS server restart restored the saved workspace")
    else:
        verify_extraction(base, args.sample, args.timeout, args.state_file)
        verify_extraction(
            base,
            args.ocr_sample,
            args.timeout,
            None,
            require_ocr=True,
        )
        print(
            "PASS server health, React UI, native and scanned OCR extraction, "
            "Excel/CSV/audit downloads"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
