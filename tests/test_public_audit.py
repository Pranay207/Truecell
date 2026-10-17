"""External-audit manifests stay pinned, UTF-8 safe, and structurally scoreable."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.public_audit import check, materialize
from truecell.models import Result, Table

ROOT = Path(__file__).resolve().parents[1]


def test_public_manifest_includes_complete_source_pinned_unicode_case():
    cases = json.loads((ROOT / "eval" / "public_cases.json").read_text(encoding="utf-8"))
    assert len({case["name"] for case in cases}) == len(cases) >= 4
    unicode_case = next(case for case in cases if case["name"] == "tabula-unicode-two-tables")
    assert "/2cdf3b4fd3f7e921dca8cc6814cdd9316be40f0f/" in unicode_case["url"]
    assert unicode_case["reference_url"].endswith("/csv/twotables.csv")
    assert sum(len(row) for table in unicode_case["tables"] for row in table["rows"]) == 126

    result = Result(
        "public.pdf",
        [
            Table(
                table["headers"],
                table["rows"],
                1,
                (0, 0, 100, 100),
                "native-lines",
            )
            for table in unicode_case["tables"]
        ],
    )
    metric = check(unicode_case, result)
    assert metric == {
        "pass": True,
        "checked_cells": 126,
        "matching_cells": 126,
        "headers_match": True,
        "shape_match": True,
    }


def test_cached_public_artifact_must_match_its_pinned_hash(tmp_path):
    artifact = tmp_path / "fixture.pdf"
    artifact.write_bytes(b"public fixture")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    materialize(artifact, "https://invalid.example/unused", digest, fetch=False)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        materialize(artifact, "https://invalid.example/unused", "0" * 64, fetch=False)
