"""Page-local orchestration; a failed page produces an audit finding, not data loss."""
from __future__ import annotations

from pathlib import Path
import logging
import time
from collections.abc import Callable

import pdfplumber

from .digital import extract_page
from .export import export_workbook
from .models import Attempt, Issue, PageReport, Result, Table
from .recover import evaluate
from .router import open_document, render_page, route_page
from .stitch import stitch
from .validate import validate

LOG = logging.getLogger(__name__)


def convert(source: str | Path, output: str | Path | None = None, *,
            recover: bool = True, progress: Callable[[int, int], None] | None = None) -> Result:
    """Extract each page, select an audited candidate, stitch, validate and export."""
    started = time.perf_counter()
    result = Result(str(source))
    fragments: list[Table] = []
    with open_document(source) as document:
        # Serialize only the active page for pdfplumber, avoiding retained full-document caches.
        for index, page in enumerate(document):
            page_started = time.perf_counter()
            report = PageReport(index + 1, "unknown")
            result.pages.append(report)
            candidates: list[tuple[float, list[Table], Attempt]] = []

            def attempt(engine: str, strategy: str, operation) -> None:
                tick = time.perf_counter()
                try:
                    tables = operation()
                    score, findings, cells = evaluate(tables)
                    record = Attempt(engine, strategy, len(tables), cells, findings,
                                     score, time.perf_counter() - tick)
                    candidates.append((score, tables, record))
                except Exception as exc:
                    record = Attempt(engine, strategy, 0, 0, 0, -10000,
                                     time.perf_counter() - tick, str(exc))
                    LOG.warning("Page %s %s failed: %s", index + 1, strategy, exc)
                report.attempts.append(record)

            try:
                report.route = route_page(page)
                if report.route == "digital":
                    import fitz
                    import io
                    with fitz.open() as single:
                        single.insert_pdf(document, from_page=index, to_page=index)
                        data = single.tobytes()
                    with pdfplumber.open(io.BytesIO(data)) as native:
                        p = native.pages[0]
                        attempt("native", "lines", lambda: extract_page(p, index + 1, "lines"))
                        if recover and (not candidates or not candidates[-1][1] or candidates[-1][2].issues):
                            attempt("native", "text", lambda: extract_page(p, index + 1, "text"))
                            attempt("native", "words", lambda: extract_page(p, index + 1, "words"))
                if report.route == "ocr" or (report.route == "digital" and not any(c[1] for c in candidates)):
                    from .ocr import extract_image, available_engines
                    engines = available_engines()
                    if not engines:
                        raise RuntimeError("No OCR engine available. Install rapidocr-onnxruntime or Tesseract.")
                    image = render_page(page)
                    attempt(engines[0], "deskew-300dpi", lambda: extract_image(image, index + 1, engines[0]))
                    if recover and (not candidates or not candidates[-1][1] or candidates[-1][2].issues):
                        attempt(engines[0], "threshold-300dpi", lambda: extract_image(image, index + 1, engines[0], alternate=True))
                        if len(engines) > 1:
                            attempt(engines[1], "second-engine", lambda: extract_image(image, index + 1, engines[1]))
                        if not any(c[1] and c[2].cells >= 12 for c in candidates):
                            for angle in (90, 180, 270):
                                attempt(engines[0], f"rotate-{angle}",
                                        lambda angle=angle: extract_image(image, index + 1, engines[0], rotation=angle))
                if recover and report.route != "empty" and (not candidates or max(candidates, key=lambda c: c[0])[2].issues
                                                             or not any(c[1] for c in candidates)):
                    from .llm_repair import configured, extract_page as vision_page
                    if configured():
                        attempt("vision-llm", "optional-vision", lambda: vision_page(render_page(page), index + 1))
                if candidates:
                    _, chosen, record = max(candidates, key=lambda c: c[0])
                    record.selected = True
                    fragments.extend(chosen)
                    report.engine = record.engine
                    report.confidence = min((t.confidence for t in chosen), default=0)
                    if not chosen:
                        result.issues.append(Issue("error", index + 1, None, None,
                                                   "No table could be reconstructed.", code="no_table"))
                    # Alternative candidates are never permitted to overwrite disagreements silently.
                    for _, alternative, alt_record in candidates:
                        if alt_record is record or not chosen or not alternative:
                            continue
                        if [t.rows for t in alternative] != [t.rows for t in chosen]:
                            result.issues.append(Issue("warning", index + 1, None, None,
                                f"Selected {record.strategy}; alternative {alt_record.strategy} produced different content or shape.",
                                "Compare the page and highlighted data.", "candidate_disagreement"))
                elif report.route == "empty":
                    result.issues.append(Issue("info", index + 1, None, None, "Empty page; no tables.", code="empty_page"))
                else:
                    raise RuntimeError("All extraction attempts failed; see Page Audit.")
            except Exception as exc:
                report.error = str(exc)
                result.issues.append(Issue("error", index + 1, None, None, str(exc), code="page_failed"))
                LOG.exception("Page %s failed", index + 1)
            report.seconds = time.perf_counter() - page_started
            LOG.info("Page %s/%s: %s, %.2fs", index + 1, len(document), report.route, report.seconds)
            if progress:
                progress(index + 1, len(document))
    result.tables, join_issues = stitch(fragments)
    result.issues.extend(join_issues)
    for i, table in enumerate(result.tables, 1):
        result.issues.extend(validate(table, i))
        for issue in list(result.issues):
            if issue.table is None and any(issue.page == p for sources in table.provenance for p, _ in sources):
                # Page-wide extraction disagreements highlight all affected source rows.
                if issue.code in {"candidate_disagreement", "page_failed"}:
                    from copy import copy
                    local = copy(issue)
                    local.table = i
                    result.issues.append(local)
    result.seconds = time.perf_counter() - started
    if output:
        export_workbook(result, output)
    return result
