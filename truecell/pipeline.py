"""Page-local orchestration; a failed page produces an audit finding, not data loss."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import pdfplumber

from .checkpoint import Checkpoints, signature, source_hash
from .constraints import analyze
from .digital import extract_page
from .export import export_workbook
from .models import Attempt, Issue, PageReport, Result, Table
from .profiling import normalize_languages, profile_page
from .recover import candidate_key, evaluate, needs_retry
from .router import open_document, render_page, route_page
from .stitch import stitch
from .validate import validate

LOG = logging.getLogger(__name__)

HIGH_VALUE_TERMS = {
    "account",
    "amount",
    "balance",
    "credit",
    "debit",
    "invoice",
    "price",
    "quantity",
    "salary",
    "tax",
    "total",
}


def _high_value_candidate(tables: list[Table]) -> bool:
    """Recognize tables where one wrong value can materially change a decision."""
    words = {
        token.lower()
        for table in tables
        for header in table.headers
        for token in header.replace("/", " ").replace("_", " ").split()
    }
    return bool(words.intersection(HIGH_VALUE_TERMS))


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
    ocr_languages: str | list[str] | tuple[str, ...] | None = None,
) -> Result:
    """Extract each page, select an audited candidate, stitch, validate and export."""
    started = time.perf_counter()
    requested_languages = normalize_languages(
        ocr_languages
        if ocr_languages is not None
        else os.environ.get("TRUECELL_OCR_LANGUAGES", "eng")
    )
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
                    "ocr_languages": requested_languages,
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
            page_profile = profile_page(page, requested_languages)
            report = PageReport(index + 1, "unknown", profile=page_profile.to_dict())
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
                report.route = "ocr" if force_ocr else route_page(page, page_profile)
                report.profile["routing_decision"] = "forced-ocr" if force_ocr else report.route
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
                native_candidate_available = any(
                    tables and record.engine == "native" for _, tables, record in candidates
                )
                report.profile["native_candidate_available"] = native_candidate_available
                native_uncertain = not candidates or needs_retry(best_tables())
                profile_cross_check = bool(report.profile.get("cross_check_recommended"))
                high_value_cross_check = (
                    bool(report.profile.get("high_value_content")) and native_uncertain
                )
                independent_cross_check = verify or (
                    recover and (profile_cross_check or high_value_cross_check)
                )
                should_run_ocr = report.route == "ocr" or (
                    report.route == "digital"
                    and (
                        independent_cross_check
                        or (not any(c[1] for c in candidates) and bool(page.get_images()))
                    )
                )
                if should_run_ocr:
                    from .ocr import (
                        available_engines,
                        engine_language_coverage,
                        extract_image,
                        order_engines,
                    )

                    engines = order_engines(available_engines(), requested_languages)
                    if not engines:
                        raise RuntimeError(
                            "No OCR engine available. Install rapidocr-onnxruntime or Tesseract."
                        )
                    coverage = {
                        engine: list(engine_language_coverage(engine, requested_languages))
                        for engine in engines
                    }
                    report.profile["ocr_engine_language_coverage"] = coverage
                    report.profile["cross_check_executed"] = bool(report.route == "digital")
                    supported = {language for values in coverage.values() for language in values}
                    missing_languages = [
                        language for language in requested_languages if language not in supported
                    ]
                    if missing_languages:
                        result.issues.append(
                            Issue(
                                "warning",
                                index + 1,
                                None,
                                None,
                                "Requested OCR language packs are unavailable: "
                                + ", ".join(missing_languages)
                                + ".",
                                "Install the matching local Tesseract language packs or provide a clearer native PDF.",
                                "ocr_language_unavailable",
                            )
                        )
                    image = render_page(page)

                    def image_tables(engine: str, **options) -> list[Table]:
                        if requested_languages == ("eng",):
                            return extract_image(image, index + 1, engine, **options)
                        return extract_image(
                            image,
                            index + 1,
                            engine,
                            languages=requested_languages,
                            **options,
                        )

                    ocr_candidate_count = len(candidates)
                    attempt(
                        engines[0],
                        "deskew-300dpi",
                        lambda: image_tables(engines[0]),
                    )
                    discovered_high_value = len(
                        candidates
                    ) > ocr_candidate_count and _high_value_candidate(candidates[-1][1])
                    if discovered_high_value:
                        report.profile["high_value_content"] = True
                        report.profile["high_value_detected_after_ocr"] = True
                    if (
                        not native_candidate_available
                        and (independent_cross_check or (recover and discovered_high_value))
                        and len(engines) > 1
                    ):
                        attempt(
                            engines[1],
                            "independent-language-aware-cross-check",
                            lambda: image_tables(engines[1]),
                        )
                    # A nonempty native candidate plus one OCR reading is already
                    # an independent check. Keep the expensive threshold,
                    # perspective and rotation ladder for OCR-routed pages or a
                    # digital page whose native strategies found no table.
                    full_ocr_recovery = report.route == "ocr" or not native_candidate_available
                    if (
                        recover
                        and full_ocr_recovery
                        and (not candidates or needs_retry(best_tables()))
                    ):
                        alternate_name = (
                            "cell-recheck-300dpi"
                            if engines[0] == "tesseract"
                            else "threshold-300dpi"
                        )
                        attempt(
                            engines[0],
                            alternate_name,
                            lambda: image_tables(engines[0], alternate=True),
                        )
                        if needs_retry(best_tables()):
                            attempt(
                                engines[0],
                                "perspective-cell-recheck-300dpi",
                                lambda: image_tables(engines[0], perspective=True, alternate=True),
                            )
                        second_already_tried = (
                            any(item.engine == engines[1] for item in report.attempts)
                            if len(engines) > 1
                            else False
                        )
                        if (
                            len(engines) > 1
                            and not second_already_tried
                            and (verify or needs_retry(best_tables()))
                        ):
                            attempt(
                                engines[1],
                                "second-engine",
                                lambda: image_tables(engines[1]),
                            )
                        # Sideways text can still produce a large, incorrect grid.
                        # Retry on substantive uncertainty, not just a low cell count.
                        if needs_retry(best_tables()):
                            hint = int(report.profile.get("rotation_hint", 0))
                            angles = tuple(
                                dict.fromkeys(
                                    ([hint] if hint in {90, 180, 270} else []) + [90, 180, 270]
                                )
                            )
                            for angle in angles:
                                attempt(
                                    engines[0],
                                    f"rotate-{angle}",
                                    lambda angle=angle: image_tables(engines[0], rotation=angle),
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
                                    lambda: image_tables(engines[1], rotation=angle),
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
