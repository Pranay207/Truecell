"""Exercise the built Windows application without using its source launcher."""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = ROOT / "portable-release" / "Truecell-Portable"
SMOKE_ROOT = ROOT / "portable-build" / "Smoke Test With Spaces"
BUNDLE = SMOKE_ROOT / "Truecell-Portable"


def request(url: str, *, data: bytes | None = None) -> bytes:
    headers = {"Content-Type": "application/json"} if data is not None else {}
    operation = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(operation, timeout=10) as response:
        if response.status not in {200, 202}:
            raise RuntimeError(f"Unexpected HTTP {response.status}: {url}")
        return response.read()


def json_request(url: str, *, data: bytes | None = None) -> dict:
    return json.loads(request(url, data=data))


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def start(executable: Path, port: int, log_name: str):
    output = (SMOKE_ROOT / f"{log_name}.stdout.log").open("w", encoding="utf-8")
    error = (SMOKE_ROOT / f"{log_name}.stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(executable), "--no-browser", "--port", str(port)],
        cwd=executable.parent,
        stdout=output,
        stderr=error,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return process, output, error


def wait_for_health(base: str, process: subprocess.Popen, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    last_error = "server did not respond"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Portable process exited with {process.returncode}")
        try:
            return json_request(base + "/api/health")
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"Portable health check timed out: {last_error}")


def wait_for_job(base: str, identifier: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = json_request(base + f"/api/jobs/{identifier}")
        if job["status"] in {"complete", "partial", "failed"}:
            if job["status"] != "complete":
                raise RuntimeError(
                    f"Portable extraction ended as {job['status']}: {job.get('error')}"
                )
            return job
        time.sleep(0.3)
    raise RuntimeError(f"Portable extraction timed out: {identifier}")


def expected_tables(name: str) -> list[dict]:
    truth = json.loads((ROOT / "samples" / f"{name}.truth.json").read_text(encoding="utf-8"))
    return truth["tables"]


def verify_sample(base: str, name: str, timeout: float) -> str:
    encoded = urllib.parse.quote(name + ".pdf")
    created = json_request(base + f"/api/samples/{encoded}", data=b"{}")
    job = wait_for_job(base, created["id"], timeout)
    actual = job["result"]["tables"]
    truth = expected_tables(name)
    assert len(actual) == len(truth)
    for observed, expected in zip(actual, truth, strict=True):
        assert observed["headers"] == expected["headers"]
        assert observed["rows"] == expected["rows"]
    workbook = request(base + f"/api/jobs/{created['id']}/export.xlsx")
    assert workbook.startswith(b"PK") and len(workbook) > 5_000
    audit = json.loads(request(base + f"/api/jobs/{created['id']}/audit.json"))
    assert audit["tables"]
    return created["id"]


def stop(process: subprocess.Popen, streams: tuple) -> None:
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    for stream in streams:
        stream.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Skip the RapidOCR scan case.")
    args = parser.parse_args()
    executable = SOURCE_BUNDLE / "Truecell.exe"
    if not executable.is_file():
        print("Build portable-release/Truecell-Portable first.")
        return 2

    if SMOKE_ROOT.exists():
        shutil.rmtree(SMOKE_ROOT)
    SMOKE_ROOT.mkdir(parents=True)
    shutil.copytree(SOURCE_BUNDLE, BUNDLE)
    executable = BUNDLE / "Truecell.exe"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    process, output, error = start(executable, port, "first-run")
    identifiers = []
    try:
        health = wait_for_health(base, process)
        assert health["status"] == "ok"
        assert health["offline"] is True
        assert health["ocr_engines"] == ["rapidocr"]
        assert b'<div id="root"></div>' in request(base + "/")
        identifiers.append(verify_sample(base, "A_invoice_register", 120))
        if not args.quick:
            identifiers.append(verify_sample(base, "C_scanned_inventory", 360))
    finally:
        stop(process, (output, error))

    # A second process must discover workspaces saved by the first one.
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    process, output, error = start(executable, port, "restart")
    try:
        wait_for_health(base, process)
        saved = json_request(base + "/api/jobs")["jobs"]
        saved_ids = {job["id"] for job in saved}
        assert set(identifiers) <= saved_ids
    finally:
        stop(process, (output, error))

    print(
        "PASS portable EXE: health, React UI, exact native extraction, "
        + ("RapidOCR scan, " if not args.quick else "")
        + "Excel/audit downloads, path with spaces, workspace restart"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
