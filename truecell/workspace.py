"""Local persistent workspaces with atomic JSON writes and immutable baselines."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import Result
from .review import digest, history_valid

ROOT = Path(__file__).resolve().parents[1] / "outputs" / "jobs"


def verify_source(folder: Path, result: Result) -> None:
    """Bind saved evidence to the actual local source bytes, not just a filename."""
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    name = metadata["source"]
    if Path(name).name != name or not name.startswith("source."):
        raise ValueError("Invalid saved source path.")
    source = folder / name
    if source.is_symlink() or source.resolve().parent != folder.resolve():
        raise ValueError("Invalid saved source path.")
    if (
        result.source_sha256
        and hashlib.sha256(source.read_bytes()).hexdigest() != result.source_sha256
    ):
        raise ValueError("Saved source changed; re-extract it before reviewing evidence.")


def atomic_json(path: Path, value: dict) -> None:
    """Replace a JSON file only after a complete, flushed serialization."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows indexers and virus scanners can briefly retain a read handle
        # after the metadata file is opened. Keep the atomic replacement and
        # retry only that transient sharing failure for a bounded interval.
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (2**attempt))
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def job_path(job_id: str, root: Path = ROOT) -> Path:
    """Resolve only generated job identifiers inside the workspace."""
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Invalid workspace identifier.")
    return root / job_id


def create_job(filename: str, content: bytes, root: Path = ROOT) -> tuple[str, Path]:
    """Store a source copy without using an untrusted filename as a path."""
    identifier = uuid.uuid4().hex
    suffix = Path(filename).suffix.lower()
    if suffix not in {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".bmp",
        ".webp",
    }:
        raise ValueError("Unsupported source document type.")
    folder = job_path(identifier, root)
    folder.mkdir(parents=True)
    source = folder / ("source" + suffix)
    source.write_bytes(content)
    atomic_json(
        folder / "metadata.json",
        {
            "id": identifier,
            "name": Path(filename).name,
            "created": datetime.now(timezone.utc).isoformat(),
            "status": "ready",
            "source": source.name,
        },
    )
    return identifier, source


def set_status(job_id: str, status: str, root: Path = ROOT, **fields) -> None:
    """Persist the processing profile and interrupted/failed state for resume."""
    path = job_path(job_id, root) / "metadata.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(status=status, **fields)
    atomic_json(path, record)


def save_result(job_id: str, result: Result, root: Path = ROOT) -> None:
    """Save the current result; retain the first extraction as an immutable baseline."""
    folder = job_path(job_id, root)
    verify_source(folder, result)
    if not history_valid(result):
        raise ValueError("Cannot save an inconsistent correction history.")
    payload = result.to_dict()
    if not (folder / "baseline.json").exists():
        atomic_json(folder / "baseline.json", {"sha256": digest(payload), "result": payload})
    atomic_json(folder / "current.json", {"sha256": digest(payload), "result": payload})
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    metadata.update(
        status="partial" if any(page.error for page in result.pages) else "complete",
        tables=len(result.tables),
        rows=sum(len(t.rows) for t in result.tables),
    )
    atomic_json(folder / "metadata.json", metadata)


def load_result(job_id: str, root: Path = ROOT, baseline: bool = False) -> Result:
    """Verify persisted payload integrity before restoring a result."""
    folder = job_path(job_id, root)
    payload = json.loads(
        (folder / ("baseline.json" if baseline else "current.json")).read_text(encoding="utf-8")
    )
    if digest(payload["result"]) != payload["sha256"]:
        raise ValueError("Saved result changed unexpectedly; use the original extraction.")
    result = Result.from_dict(payload["result"])
    verify_source(folder, result)
    if not history_valid(result):
        raise ValueError("Saved correction history is inconsistent.")
    return result


def list_jobs(root: Path = ROOT) -> list[dict]:
    """List metadata only; a damaged individual record cannot hide other jobs."""
    if not root.exists():
        return []
    records = []
    for folder in root.iterdir():
        try:
            record = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            if not isinstance(record, dict) or any(
                not isinstance(record.get(key), str) or not record[key]
                for key in ("id", "name", "created", "status", "source")
            ):
                continue
            if job_path(record["id"], root).name != folder.name:
                continue
            created = datetime.fromisoformat(record["created"])
            if created.tzinfo is None:
                continue
            if record["status"] not in {"ready", "processing", "complete", "partial", "failed"}:
                continue
            if Path(record["source"]).name != record["source"] or not record["source"].startswith(
                "source."
            ):
                continue
            if "options" in record and not isinstance(record["options"], dict):
                continue
            records.append(record)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(records, key=lambda r: datetime.fromisoformat(r["created"]), reverse=True)
