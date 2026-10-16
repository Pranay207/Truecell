"""Page-local orchestration; a failed page produces an audit finding, not data loss."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

import pdfplumber

from .checkpoint import Checkpoints, signature, source_hash
from .constraints import analyze
from .digital import extract_page
from .export import export_workbook
from .models import Attempt, Issue, PageReport, Result, Table
from .recover import candidate_key, evaluate, needs_retry
from .router import open_document, render_page, route_page
from .stitch import stitch
from .validate import validate

LOG = logging.getLogger(__name__)


def convert(
    source: str | Path,
    output: str | Path | None = None,
    *,
    recover: bool = True,
    progress: Callable[[int, int], None] | None = None,
    verify: bool = False,
    checkpoint_dir: str | Path | None = None,
    force_ocr: bool = False,
    allow_cloud: bool = False,
) -> Result:
    """Extract each page, select an audited candidate, stitch, validate and export."""
    started = time.perf_counter()
    result = Result(Path(source).name)
    result.source_sha256 = source_hash(source)
    cache = (
        Checkpoints(
            Path(checkpoint_dir),
            signature(
                result.source_sha256,
                {
                    "recover": recover,
                    "verify": verify,
                    "force_ocr": force_ocr,
                    "allow_cloud": allow_cloud,
                },
            ),
        )
        if checkpoint_dir
        else None
    )
    fragments: list[Table] = []
    with open_document(source) as document:
        # Serialize only the active page for pdfplumber, avoiding retained full-document caches.
        for index, page in enumerate(document):
            page_started = time.perf_counter()
            cached = cache.load(index + 1) if cache else None
            if cached:
                tables, report, issues = cached
                fragments.extend(tables)
                result.pages.append(report)
                result.issues.extend(issues)
                LOG.info("Page %s/%s: verified checkpoint", index + 1, len(document))
                if progress:
                    progress(index + 1, len(document))
                continue
            report = PageReport(index + 1, "unknown")
            result.pages.append(report)
            candidates: list[tuple[float, list[Table], Attempt]] = []

            def best_tables() -> list[Table]:
                best = max(candidates, key=candidate_key, default=None)
                return best[1] if best else []

            def attempt(engine: str, strategy: str, operation) -> None:
                tick = time.perf_counter()
                try:
                    tables = operation()
                    score, findings, cells = evaluate(tables)
                    record = Attempt(
                        engine,
                        strategy,
                        len(tables),
                        cells,
                        findings,
                        score,
                        time.perf_counter() - tick,
                    )
                    candidates.append((score, tables, record))
                except Exception as exc:
                    error = str(exc) or type(exc).__name__
                    record = Attempt(
                        engine,
                        strategy,
                        0,
                        0,
                        0,
                        -10000,
                        time.perf_counter() - tick,
                        error,
                    )
                    LOG.warning("Page %s %s failed: %s", index + 1, strategy, error)
                report.attempts.append(record)

            try:
                report.route = "ocr" if force_ocr else route_page(page)
                if report.route == "digital":
                    import io

                    import fitz

                    with fitz.open() as single:
                        single.insert_pdf(document, from_page=index, to_page=index)
                        data = single.tobytes()
                    with pdfplumber.open(io.BytesIO(data)) as native:
                        p = native.pages[0]
                        attempt(
                            "native",
                            "lines",
                            lambda: extract_page(p, index + 1, "lines"),
                        )
                        if recover and (not candidates or needs_retry(candidates[-1][1])):
                            attempt(
                                "native",
                                "text",
                                lambda: extract_page(p, index + 1, "text"),
                            )
                            attempt(
                                "native",
                                "words",
                                lambda: extract_page(p, index + 1, "words"),
                            )
                if report.route == "ocr" or (
                    report.route == "digital"
                    and (verify or (not any(c[1] for c in candidates) and bool(page.get_images())))
                ):
                    from .ocr import available_engines, extract_image

                    engines = available_engines()
                    if not engines:
                        raise RuntimeError(
                            "No OCR engine available. Install rapidocr-onnxruntime or Tesseract."
                        )
                    image = render_page(page)
                    attempt(
                        engines[0],
                        "deskew-300dpi",
                        lambda: extract_image(image, index + 1, engines[0]),
                    )
                    if recover and (not candidates or needs_retry(candidates[-1][1])):
                        alternate_name = (
                            "cell-recheck-300dpi"
                            if engines[0] == "tesseract"
                            else "threshold-300dpi"
                        )
                        attempt(
                            engines[0],
                            alternate_name,
                            lambda: extract_image(image, index + 1, engines[0], alternate=True),
                        )
                        if needs_retry(best_tables()):
                            attempt(
                                engines[0],
                                "perspective-cell-recheck-300dpi",
                                lambda: extract_image(
                                    image,
                                    index + 1,
                                    engines[0],
                                    perspective=True,
                                    alternate=True,
                                ),
                            )
                        if len(engines) > 1 and (verify or needs_retry(best_tables())):
                            attempt(
                                engines[1],
                                "second-engine",
                                lambda: extract_image(image, index + 1, engines[1]),
                            )
                        # Sideways text can still produce a large, incorrect grid.
                        # Retry on substantive uncertainty, not just a low cell count.
                        if needs_retry(best_tables()):
                            for angle in (90, 180, 270):
                                attempt(
                                    engines[0],
                                    f"rotate-{angle}",
                                    lambda angle=angle: extract_image(
                                        image, index + 1, engines[0], rotation=angle
                                    ),
                                )
                                if not needs_retry(best_tables()):
                                    break
                            best = max(candidates, key=candidate_key, default=None)
                            if (
                                len(engines) > 1
                                and best
                                and best[2].strategy.startswith("rotate-")
                                and needs_retry(best[1])
                            ):
                                angle = int(best[2].strategy.rsplit("-", 1)[1])
                                attempt(
                                    engines[1],
                                    f"rotate-{angle}-second-engine",
                                    lambda: extract_image(
                                        image, index + 1, engines[1], rotation=angle
                                    ),
                                )
                if (
                    allow_cloud
                    and recover
                    and report.route != "empty"
                    and (
                        not candidates
                        or max(candidates, key=candidate_key)[2].issues
                        or not any(c[1] for c in candidates)
                    )
                ):
                    from .llm_repair import configured
                    from .llm_repair import extract_page as vision_page

                    if configured():
                        attempt(
                            "vision-llm",
                            "optional-vision",
                            lambda: vision_page(render_page(page), index + 1),
                        )
                if candidates:
                    _, chosen, record = max(candidates, key=candidate_key)
                    record.selected = True
                    fragments.extend(chosen)
                    report.engine = record.engine
                    report.confidence = min((t.confidence for t in chosen), default=0)
                    if not chosen:
                        result.issues.append(
                            Issue(
                                "error",
                                index + 1,
                                None,
                                None,
                                "No table could be reconstructed.",
                                code="no_table",
                            )
                        )
                    # Alternative candidates are never permitted to overwrite disagreements silently.
                    for _, alternative, alt_record in candidates:
                        if alt_record is record or not chosen or not alternative:
                            continue
                        same_grid = len(chosen) == len(alternative) and all(
                            t.headers == a.headers
                            and len(t.rows) == len(a.rows)
                            and all(len(r) == len(s) for r, s in zip(t.rows, a.rows))
                            for t, a in zip(chosen, alternative)
                        )
                        if same_grid:
                            for target, other in zip(chosen, alternative):
                                for r, row in enumerate(target.rows):
                                    for c, value in enumerate(row):
                                        if value != other.rows[r][c]:
                                            sources = other.cell_sources[r][c] or [
                                                {
                                                    "page": index + 1,
                                                    "bbox": None,
                                                    "text": other.rows[r][c],
                                                    "engine": other.engine,
                                                    "confidence": None,
                                                }
                                            ]
                                            target.cell_sources[r][c].extend(
                                                [
                                                    {
                                                        **s,
                                                        "role": "comparison",
                                                        "strategy": alt_record.strategy,
                                                    }
                                                    for s in sources
                                                ]
                                            )
                        elif [t.rows for t in alternative] != [t.rows for t in chosen] or [
                            t.headers for t in alternative
                        ] != [t.headers for t in chosen]:
                            result.issues.append(
                                Issue(
                                    "warning",
                                    index + 1,
                                    None,
                                    None,
                                    f"Selected {record.strategy}; alternative {alt_record.strategy} produced different content or shape.",
                                    "Compare the page and highlighted data.",
                                    "candidate_disagreement",
                                )
                            )
                elif report.route == "empty":
                    result.issues.append(
                        Issue(
                            "info",
                            index + 1,
                            None,
                            None,
                            "Empty page; no tables.",
                            code="empty_page",
                        )
                    )
                else:
                    raise RuntimeError("All extraction attempts failed; see Page Audit.")
            except Exception as exc:
                report.error = str(exc) or type(exc).__name__
                result.issues.append(
                    Issue("error", index + 1, None, None, report.error, code="page_failed")
                )
                LOG.exception("Page %s failed", index + 1)
            report.seconds = time.perf_counter() - page_started
            if cache:
                selected = next((c[1] for c in candidates if c[2].selected), [])
                try:
                    cache.save(
                        index + 1,
                        selected,
                        report,
                        [i for i in result.issues if i.page == index + 1],
                    )
                except OSError as exc:
                    LOG.warning("Could not save page checkpoint: %s", exc)
            LOG.info(
                "Page %s/%s: %s, %.2fs",
                index + 1,
                len(document),
                report.route,
                report.seconds,
            )
            if progress:
                progress(index + 1, len(document))
    result.tables, join_issues = stitch(fragments)
    result.issues.extend(join_issues)
    for i, table in enumerate(result.tables, 1):
        result.issues.extend(validate(table, i))
        for issue in list(result.issues):
            if issue.table is None and any(
                issue.page == p for sources in table.provenance for p, _ in sources
            ):
                # Page-wide extraction disagreements highlight all affected source rows.
                if issue.code in {"candidate_disagreement", "page_failed"}:
                    from copy import copy

                    local = copy(issue)
                    local.table = i
                    result.issues.append(local)
    analyze(result)
    result.review = {"status": "unreviewed"}
    result.seconds = time.perf_counter() - started
    if output:
        export_workbook(result, output)
    return result
