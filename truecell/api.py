"""Local HTTP adapter for the existing offline extraction/review engine.

Run with ``python -m uvicorn truecell.api:app --host 127.0.0.1 --port 8503``.
The launcher can explicitly enable access from a private LAN for phone testing.
"""

from __future__ import annotations

import io
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr
from starlette.concurrency import run_in_threadpool

from .assurance import challenge
from .constraints import analyze, coverage
from .export import export_workbook
from .models import Result
from .ocr import available_engines
from .pipeline import convert
from .review import apply_edit, complete_review, fingerprint, review_current
from .router import IMAGE_EXTENSIONS, MAX_PAGES, open_document, render_page
from .validate import validate
from .workspace import (
    ROOT,
    create_job,
    job_path,
    list_jobs,
    load_result,
    save_result,
    set_status,
)

PROJECT = Path(__file__).resolve().parents[1]
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
EXTRACTION_CODES = {
    "candidate_disagreement",
    "page_failed",
    "no_table",
    "empty_page",
    "inferred_join",
    "split_row_join",
}
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
PRIVATE_LAN_NETWORKS = tuple(
    ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def private_lan_address(value: str) -> bool:
    """Return whether a literal IPv4 address belongs to an RFC 1918 LAN."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and any(address in network for network in PRIVATE_LAN_NETWORKS)


def environment_lan_host() -> str | None:
    """Read and validate the exact LAN host supplied by the launcher."""
    host = os.environ.get("TRUECELL_LAN_HOST", "").strip()
    if not host:
        return None
    if not private_lan_address(host):
        raise RuntimeError("TRUECELL_LAN_HOST must be an RFC 1918 IPv4 address.")
    return host


class ProcessOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verify: StrictBool = False
    force_ocr: StrictBool = False


class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fingerprint: StrictStr | None = None


class CellEdit(SnapshotRequest):
    table: StrictInt
    row: StrictInt
    column: StrictInt
    value: StrictStr = Field(max_length=1_000_000)
    note: StrictStr = Field(min_length=1, max_length=20_000)


class PreviewEdit(CellEdit):
    note: StrictStr = Field(default="Counterfactual preview only", min_length=1, max_length=20_000)


class ChallengeRequest(SnapshotRequest):
    table: StrictInt


class SourceReview(SnapshotRequest):
    source_checked: StrictBool
    note: StrictStr = Field(min_length=1, max_length=20_000)


class WorkspaceDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: StrictStr = Field(min_length=1, max_length=255)


class _Jobs:
    def __init__(self, root: Path, samples: Path, runner: Callable, maximum: int):
        self.root = root
        self.samples = samples
        self.runner = runner
        self.maximum = maximum
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="truecell")
        self.slots = threading.BoundedSemaphore(3)
        self.active: set[str] = set()

    def folder(self, identifier: str) -> Path:
        try:
            folder = job_path(identifier, self.root)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if folder.is_symlink() or folder.resolve().parent != self.root.resolve():
            raise HTTPException(400, "Invalid workspace path.")
        if (folder / "metadata.json").is_symlink():
            raise HTTPException(400, "Invalid workspace metadata path.")
        if not (folder / "metadata.json").is_file():
            raise HTTPException(404, "Workspace not found.")
        return folder

    def metadata(self, identifier: str) -> dict:
        folder = self.folder(identifier)
        try:
            metadata = json.loads((folder / "metadata.json").read_text("utf-8"))
            if not isinstance(metadata, dict) or metadata.get("id") != identifier:
                raise ValueError("Workspace identifier mismatch.")
            if any(not isinstance(metadata.get(key), str) for key in ("name", "status", "source")):
                raise ValueError("Incomplete workspace metadata.")
            return metadata
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, "Workspace metadata is damaged.") from exc

    def source(self, identifier: str) -> Path:
        folder = self.folder(identifier)
        name = self.metadata(identifier).get("source", "")
        if not isinstance(name, str) or Path(name).name != name or not name.startswith("source."):
            raise HTTPException(409, "Invalid saved source path.")
        source = folder / name
        if source.is_symlink() or source.resolve().parent != folder.resolve():
            raise HTTPException(409, "Invalid saved source path.")
        if not source.is_file():
            raise HTTPException(404, "Saved source is unavailable.")
        return source

    def result(self, identifier: str, *, baseline: bool = False) -> Result:
        self.folder(identifier)
        try:
            return load_result(identifier, self.root, baseline=baseline)
        except FileNotFoundError as exc:
            raise HTTPException(409, "This workspace has no completed extraction yet.") from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, f"Saved extraction cannot be opened: {exc}") from exc

    def detail(self, identifier: str) -> dict:
        with self.lock:
            detail = self.metadata(identifier)
            detail.setdefault("progress", 0)
            detail.setdefault("progress_page", 0)
            detail.setdefault("progress_pages", detail.get("pages", 0))
            if (self.folder(identifier) / "current.json").is_file():
                result = self.result(identifier)
                detail.update(
                    result=result.to_dict(),
                    fingerprint=fingerprint(result),
                    coverage=coverage(result),
                    reviewed=review_current(result),
                    result_is_previous=identifier in self.active,
                )
            return detail

    def ensure_idle(self, identifier: str) -> None:
        self.folder(identifier)
        if identifier in self.active:
            raise HTTPException(
                409, "Wait for extraction to finish before changing this workspace."
            )

    @staticmethod
    def check_snapshot(result: Result, expected: str | None) -> None:
        if expected is not None and expected != fingerprint(result):
            raise HTTPException(409, "The workspace changed. Reload it before saving this change.")

    def start(self, identifier: str, options: ProcessOptions) -> None:
        with self.lock:
            self.ensure_idle(identifier)
            source = self.source(identifier)
            if (self.folder(identifier) / "current.json").exists():
                current = self.result(identifier)
                if current.history or current.review.get("status") == "reviewed":
                    raise HTTPException(
                        409, "This workspace has reviewed changes. Upload a new copy to re-extract."
                    )
            if not self.slots.acquire(blocking=False):
                raise HTTPException(429, "The local worker queue is full. Try again shortly.")
            self.active.add(identifier)
            try:
                set_status(
                    identifier,
                    "processing",
                    self.root,
                    options=options.model_dump(),
                    progress=0,
                    progress_page=0,
                    error="",
                    message="Queued for the local worker.",
                )
                self.executor.submit(self._process, identifier, source, options)
            except Exception:
                self.active.discard(identifier)
                self.slots.release()
                raise

    def _process(self, identifier: str, source: Path, options: ProcessOptions) -> None:
        def progress(page: int, pages: int) -> None:
            with self.lock:
                set_status(
                    identifier,
                    "processing",
                    self.root,
                    progress=page / pages,
                    progress_page=page,
                    progress_pages=pages,
                    message=f"Processed page {page} of {pages}.",
                )

        try:
            result = self.runner(
                source,
                verify=options.verify,
                force_ocr=options.force_ocr,
                allow_cloud=False,
                checkpoint_dir=self.folder(identifier) / "pages",
                progress=progress,
            )
            with self.lock:
                result.source = self.metadata(identifier)["name"]
                save_result(identifier, result, self.root)
                status = "partial" if any(page.error for page in result.pages) else "complete"
                set_status(
                    identifier,
                    status,
                    self.root,
                    progress=1,
                    progress_page=len(result.pages),
                    progress_pages=len(result.pages),
                    error="",
                    message="Some pages need recovery."
                    if status == "partial"
                    else "Extraction complete.",
                )
        except Exception as exc:
            with self.lock:
                set_status(identifier, "failed", self.root, error=str(exc)[:2000])
        finally:
            with self.lock:
                self.active.discard(identifier)
                self.slots.release()

    def upload(self, filename: str, content: bytes, options: ProcessOptions) -> str:
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        try:
            filename.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HTTPException(400, "The document filename is not valid Unicode.") from exc
        if len(filename) > 255 or any(
            ord(character) < 32 or ord(character) == 127 for character in filename
        ):
            raise HTTPException(
                400, "Use a filename without control characters, at most 255 characters."
            )
        if not content:
            raise HTTPException(400, "The uploaded document is empty.")
        if len(content) > self.maximum:
            raise HTTPException(413, "Document exceeds the configured upload size limit.")
        suffix = Path(filename).suffix.lower()
        if suffix not in IMAGE_EXTENSIONS | {".pdf"}:
            raise HTTPException(400, "Upload a PDF or supported scanned image.")
        try:
            with TemporaryDirectory(prefix="truecell-input-") as temporary:
                check = Path(temporary) / ("input" + suffix)
                check.write_bytes(content)
                with open_document(check) as document:
                    pages = len(document)
        except (OSError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        with self.lock:
            if len(self.active) >= 3:
                raise HTTPException(429, "The local worker queue is full. Try again shortly.")
            identifier, _ = create_job(filename, content, self.root)
            set_status(identifier, "ready", self.root, pages=pages, progress_pages=pages)
            self.start(identifier, options)
            return identifier


def create_app(
    root: Path | None = None,
    *,
    samples: Path | None = None,
    runner: Callable = convert,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    frontend: Path | None = None,
    lan_host: str | None = None,
) -> FastAPI:
    """Create a local API; injectable roots/runner keep tests away from real jobs."""
    if lan_host is not None and not private_lan_address(lan_host):
        raise ValueError("LAN host must be an RFC 1918 IPv4 address.")
    jobs = _Jobs(Path(root or ROOT), Path(samples or PROJECT / "samples"), runner, max_upload_bytes)
    allowed_hosts = LOCAL_HOSTS | ({lan_host} if lan_host else set())

    @asynccontextmanager
    async def lifespan(application):
        for record in list_jobs(jobs.root):
            if record["status"] == "processing":
                set_status(
                    record["id"],
                    "failed",
                    jobs.root,
                    error="The previous app session stopped. Resume its verified page checkpoints.",
                )
        yield
        jobs.executor.shutdown(wait=True, cancel_futures=True)

    application = FastAPI(title="Truecell Local API", docs_url="/api/docs", lifespan=lifespan)
    application.state.jobs = jobs
    application.state.lan_host = lan_host
    origin_hosts = ["localhost", r"127\.0\.0\.1", r"\[::1\]"]
    if lan_host:
        origin_hosts.append(re.escape(lan_host))
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=rf"^https?://(?:{'|'.join(origin_hosts)})(?::\d+)?$",
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def local_only(request: Request, call_next):
        client = request.client.host if request.client else ""
        try:
            host = request.url.hostname
            origin = request.headers.get("origin")
            origin_parts = urlsplit(origin) if origin else None
            origin_host = origin_parts.hostname if origin_parts else None
            origin_port = origin_parts.port if origin_parts else None
        except ValueError:
            return JSONResponse({"detail": "Invalid request origin."}, status_code=403)
        client_allowed = client in LOCAL_HOSTS or (bool(lan_host) and private_lan_address(client))
        if not client_allowed or host not in allowed_hosts:
            return JSONResponse({"detail": "This device or host is not allowed."}, status_code=403)
        if origin:
            loopback_development = client in LOCAL_HOSTS and origin_host in LOCAL_HOSTS
            request_port = request.url.port
            same_lan_origin = bool(
                lan_host
                and host == lan_host
                and origin_host == lan_host
                and origin_parts
                and origin_parts.scheme == request.url.scheme
                and origin_port == request_port
            )
            if not (loopback_development or same_lan_origin):
                return JSONResponse({"detail": "This origin is not allowed."}, status_code=403)
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > jobs.maximum + 128 * 1024:
                    return JSONResponse({"detail": "Upload is too large."}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length."}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/api/health")
    def health():
        return {
            "status": "ok",
            "offline": True,
            "max_pages": MAX_PAGES,
            "max_upload_bytes": jobs.maximum,
            "ocr_engines": available_engines(),
            "network_mode": "lan" if lan_host else "loopback",
        }

    @application.get("/api/jobs")
    def saved_jobs():
        return {"jobs": list_jobs(jobs.root)}

    @application.post("/api/jobs", status_code=202)
    async def upload_job(
        file: Annotated[UploadFile, File()],
        verify: Annotated[bool, Form()] = False,
        force_ocr: Annotated[bool, Form()] = False,
    ):
        try:
            content = bytearray()
            while chunk := await file.read(min(1024 * 1024, jobs.maximum + 1)):
                content.extend(chunk)
                if len(content) > jobs.maximum:
                    raise HTTPException(413, "Document exceeds the configured upload size limit.")
            identifier = await run_in_threadpool(
                jobs.upload,
                file.filename or "document.pdf",
                bytes(content),
                ProcessOptions(verify=verify, force_ocr=force_ocr),
            )
            return await run_in_threadpool(jobs.detail, identifier)
        finally:
            await file.close()

    @application.get("/api/jobs/{identifier}")
    def job_detail(identifier: str):
        return jobs.detail(identifier)

    @application.delete("/api/jobs/{identifier}")
    def delete_job(identifier: str, request: WorkspaceDelete):
        with jobs.lock:
            jobs.ensure_idle(identifier)
            metadata = jobs.metadata(identifier)
            if request.confirmation != metadata["name"]:
                raise HTTPException(409, "Confirmation does not match the workspace name.")
            folder = jobs.folder(identifier)
            try:
                shutil.rmtree(folder)
            except OSError as exc:
                raise HTTPException(
                    409, "Workspace files are in use. Close local previews and try again."
                ) from exc
            return {"deleted": identifier, "name": metadata["name"]}

    @application.post("/api/jobs/{identifier}/process", status_code=202)
    def process_job(identifier: str, options: ProcessOptions | None = None):
        with jobs.lock:
            jobs.ensure_idle(identifier)
            metadata = jobs.metadata(identifier)
            if options is None:
                saved_options = metadata.get("options", {})
                options = ProcessOptions(
                    verify=saved_options.get("verify", False) is True,
                    force_ocr=saved_options.get("force_ocr", saved_options.get("force", False))
                    is True,
                )
            if (jobs.folder(identifier) / "current.json").exists():
                current = jobs.result(identifier)
                if current.history or review_current(current):
                    source = jobs.source(identifier)
                    if source.stat().st_size > jobs.maximum:
                        raise HTTPException(413, "Source exceeds the configured upload size limit.")
                    # Re-extract in a fresh workspace: never overwrite reviewed values/history.
                    # Its page checkpoints are recomputed rather than copying unchecked files.
                    fork = jobs.upload(metadata["name"], source.read_bytes(), options)
                    set_status(
                        fork,
                        "processing",
                        jobs.root,
                        forked_from=identifier,
                        message="New extraction; the original reviewed workspace is preserved.",
                    )
                    return jobs.detail(fork)
            jobs.start(identifier, options)
            return jobs.detail(identifier)

    @application.get("/api/jobs/{identifier}/result")
    def job_result(identifier: str):
        result = jobs.result(identifier)
        return {
            "result": result.to_dict(),
            "fingerprint": fingerprint(result),
            "coverage": coverage(result),
        }

    @application.patch("/api/jobs/{identifier}/cells")
    @application.post("/api/jobs/{identifier}/edit", include_in_schema=False)
    def edit_cell(identifier: str, edit: CellEdit):
        with jobs.lock:
            jobs.ensure_idle(identifier)
            result = jobs.result(identifier)
            jobs.check_snapshot(result, edit.fingerprint)
            try:
                changed = apply_edit(
                    result, edit.table, edit.row, edit.column, edit.value, edit.note
                )
                save_result(identifier, changed, jobs.root)
            except (ValueError, IndexError) as exc:
                raise HTTPException(400, str(exc)) from exc
            return jobs.detail(identifier)

    @application.post("/api/jobs/{identifier}/preview")
    def preview_cell(identifier: str, edit: PreviewEdit):
        # Synchronous FastAPI routes run in its worker threadpool. Only snapshot loading
        # takes the workspace lock; disposable arithmetic must not block status polling.
        with jobs.lock:
            jobs.ensure_idle(identifier)
            result = jobs.result(identifier)
            jobs.check_snapshot(result, edit.fingerprint)
        try:
            proposed = apply_edit(result, edit.table, edit.row, edit.column, edit.value, edit.note)
        except (ValueError, IndexError) as exc:
            raise HTTPException(400, str(exc)) from exc

        def counts(snapshot: Result) -> dict:
            return {
                "findings": len(snapshot.issues),
                "failed_equation_checks": sum(
                    len(relation["violations"]) for relation in snapshot.constraints
                ),
            }

        return {
            "table": edit.table,
            "row": edit.row,
            "column": edit.column,
            "observed": proposed.history[-1]["before"],
            "proposed": edit.value,
            "before": counts(result),
            "after": counts(proposed),
            "fingerprint": fingerprint(result),
            "saved": False,
        }

    @application.post("/api/jobs/{identifier}/challenge")
    def challenge_validator(identifier: str, request: ChallengeRequest):
        with jobs.lock:
            jobs.ensure_idle(identifier)
            result = jobs.result(identifier)
            jobs.check_snapshot(result, request.fingerprint)
        if not 0 <= request.table < len(result.tables):
            raise HTTPException(400, "Invalid table index.")
        disposable = deepcopy(result.tables[request.table])
        rows_available = len(disposable.rows)
        # Match the Studio lab's bounded scope, keeping page provenance aligned.
        disposable.rows = disposable.rows[:120]
        disposable.provenance = disposable.provenance[:120]
        disposable.cell_sources = disposable.cell_sources[:120]
        disposable.row_engines = disposable.row_engines[:120]
        disposable.cell_confidence = {
            (row, column): score
            for (row, column), score in disposable.cell_confidence.items()
            if row < 120
        }
        report = challenge(disposable, 24)
        return {
            **report,
            "table": request.table,
            "fingerprint": fingerprint(result),
            "saved": False,
            "row_limit": 120,
            "rows_available": rows_available,
            "rows_tested": len(disposable.rows),
        }

    @application.post("/api/jobs/{identifier}/review")
    def record_review(identifier: str, review: SourceReview):
        with jobs.lock:
            jobs.ensure_idle(identifier)
            result = jobs.result(identifier)
            jobs.check_snapshot(result, review.fingerprint)
            try:
                changed = complete_review(result, review.source_checked, review.note)
                save_result(identifier, changed, jobs.root)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return jobs.detail(identifier)

    @application.post("/api/jobs/{identifier}/revalidate")
    def revalidate(identifier: str, snapshot: SnapshotRequest):
        with jobs.lock:
            jobs.ensure_idle(identifier)
            result = jobs.result(identifier)
            jobs.check_snapshot(result, snapshot.fingerprint)
            working = deepcopy(result)
            working.issues = [issue for issue in working.issues if issue.code in EXTRACTION_CODES]
            for index, table in enumerate(working.tables, 1):
                working.issues.extend(validate(table, index))
            analyze(working)
            if fingerprint(working) != fingerprint(result):
                working.review = {"status": "unreviewed", "reason": "Validation findings changed."}
            save_result(identifier, working, jobs.root)
            return jobs.detail(identifier)

    @application.get("/api/jobs/{identifier}/evidence")
    def evidence(identifier: str, table: int, row: int, column: int):
        result = jobs.result(identifier)
        if not 0 <= table < len(result.tables):
            raise HTTPException(400, "Invalid table index.")
        target = result.tables[table]
        if not -1 <= row < len(target.rows):
            raise HTTPException(400, "Invalid source row.")
        values = target.headers if row == -1 else target.rows[row]
        if not 0 <= column < len(values):
            raise HTTPException(400, "Invalid column index.")
        records = target.header_sources[column] if row == -1 else target.cell_sources[row][column]
        return {"value": values[column], "sources": records}

    def checked_source(identifier: str) -> Path:
        source = jobs.source(identifier)
        if (jobs.folder(identifier) / "current.json").is_file():
            jobs.result(identifier)  # Verify original bytes before showing source evidence.
        return source

    @application.get("/api/jobs/{identifier}/source")
    def source_document(identifier: str):
        source = checked_source(identifier)
        return FileResponse(
            source,
            media_type=mimetypes.guess_type(source)[0] or "application/octet-stream",
            filename=jobs.metadata(identifier)["name"],
            content_disposition_type="inline",
        )

    @application.get("/api/jobs/{identifier}/pages/{page}/info")
    def page_info(identifier: str, page: int):
        with open_document(checked_source(identifier)) as document:
            if not 1 <= page <= len(document):
                raise HTTPException(404, "Source page not found.")
            return {
                "width": document[page - 1].rect.width,
                "height": document[page - 1].rect.height,
            }

    @application.get("/api/jobs/{identifier}/pages/{page}/image")
    @application.get("/api/jobs/{identifier}/pages/{page}.png", include_in_schema=False)
    def page_image(identifier: str, page: int, dpi: Annotated[int, Query(ge=72, le=180)] = 130):
        with open_document(checked_source(identifier)) as document:
            if not 1 <= page <= len(document):
                raise HTTPException(404, "Source page not found.")
            image = render_page(document[page - 1], dpi)
            stream = io.BytesIO()
            image.save(stream, format="PNG")
        return Response(stream.getvalue(), media_type="image/png")

    @application.get("/api/jobs/{identifier}/export.xlsx")
    def excel_download(identifier: str):
        result = jobs.result(identifier)
        with TemporaryDirectory(prefix="truecell-xlsx-") as temporary:
            output = export_workbook(result, Path(temporary) / "result.xlsx")
            content = output.read_bytes()
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="truecell-result.xlsx"'},
        )

    def audit_response(identifier: str, baseline: bool = False):
        result = jobs.result(identifier, baseline=baseline)
        return Response(
            json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="truecell-audit.json"'},
        )

    @application.get("/api/jobs/{identifier}/audit.json")
    def audit_download(identifier: str):
        return audit_response(identifier)

    @application.get("/api/jobs/{identifier}/baseline.json")
    def baseline_download(identifier: str):
        return audit_response(identifier, baseline=True)

    def sample_files() -> dict[str, Path]:
        return {
            path.name: path
            for path in sorted(jobs.samples.glob("*.pdf"))
            if path.is_file()
            and not path.is_symlink()
            and path.resolve().parent == jobs.samples.resolve()
        }

    @application.get("/api/samples")
    def samples_list():
        return {
            "samples": [
                {"filename": name, "name": Path(name).stem.replace("_", " ")}
                for name in sample_files()
            ]
        }

    @application.post("/api/samples/{filename}", status_code=202)
    def sample_job(filename: str, options: ProcessOptions | None = None):
        path = sample_files().get(filename)
        if path is None:
            raise HTTPException(404, "Sample document not found.")
        if path.stat().st_size > jobs.maximum:
            raise HTTPException(413, "Sample exceeds the upload size limit.")
        identifier = jobs.upload(filename, path.read_bytes(), options or ProcessOptions())
        return jobs.detail(identifier)

    distribution = Path(frontend or PROJECT / "frontend" / "dist")
    if (distribution / "index.html").is_file():
        application.mount("/", StaticFiles(directory=distribution, html=True), name="studio")
    else:

        @application.get("/", include_in_schema=False)
        def frontend_not_built():
            return JSONResponse(
                {
                    "message": "The Studio frontend build is missing. The local API is running.",
                    "setup": "Restore the supplied frontend/dist folder or build the frontend once.",
                    "api": "/api/health",
                },
                status_code=503,
            )

    return application


app = create_app(lan_host=environment_lan_host())
