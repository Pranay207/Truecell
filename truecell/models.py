"""Shared, serializable extraction records. Coordinates use page points."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Issue:
    severity: str
    page: int
    row: int | None
    column: int | None
    reason: str
    suggestion: str = "Review the source document."
    code: str = "review"
    table: int | None = None


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    page: int
    bbox: tuple[float, float, float, float]
    engine: str
    confidence: float = 1.0
    header_detected: bool = True
    provenance: list[list[tuple[int, int]]] = field(default_factory=list)
    cell_confidence: dict[tuple[int, int], float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    row_engines: list[str] = field(default_factory=list)
    cell_sources: list[list[list[dict[str, Any]]]] = field(default_factory=list)
    header_sources: list[list[dict[str, Any]]] = field(default_factory=list)
    page_summaries: list[dict[str, Any]] = field(default_factory=list)
    join_receipt: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provenance:
            self.provenance = [[(self.page, i + 1)] for i in range(len(self.rows))]
        else:
            self.provenance = [[tuple(pair) for pair in sources] for sources in self.provenance]
        if not self.row_engines:
            self.row_engines = [self.engine] * len(self.rows)
        if not self.cell_sources:
            self.cell_sources = [[[] for _ in row] for row in self.rows]
        if not self.header_sources:
            self.header_sources = [[] for _ in self.headers]

    def to_dict(self) -> dict[str, Any]:
        """Serialize recognition scores without unsafe tuple-keyed JSON objects."""
        value = asdict(self)
        value.pop("cell_confidence")
        value["cell_scores"] = [
            [r, c, score] for (r, c), score in sorted(self.cell_confidence.items())
        ]
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Table:
        """Restore a table from a local checkpoint or exported audit."""
        data = dict(value)
        scores = data.pop("cell_scores", [])
        data["cell_confidence"] = {(r, c): score for r, c, score in scores}
        return cls(**data)


@dataclass
class Attempt:
    engine: str
    strategy: str
    tables: int
    cells: int
    issues: int
    score: float
    seconds: float
    error: str = ""
    selected: bool = False
    candidate_id: str = ""
    phase: str = ""
    execution: str = "sequential"
    rank: int | None = None
    selection_reason: str = ""


@dataclass
class PageReport:
    page: int
    route: str
    engine: str = "none"
    confidence: float = 0
    seconds: float = 0
    attempts: list[Attempt] = field(default_factory=list)
    error: str = ""
    profile: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    source: str
    tables: list[Table] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    pages: list[PageReport] = field(default_factory=list)
    seconds: float = 0
    source_sha256: str = ""
    constraints: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    review: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe audit records, omitting tuple-keyed OCR internals."""
        value = asdict(self)
        value["tables"] = [table.to_dict() for table in self.tables]
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Result:
        """Load an audit without importing code or executing document content."""
        data = dict(value)
        data["tables"] = [Table.from_dict(t) for t in data.get("tables", [])]
        data["issues"] = [Issue(**i) for i in data.get("issues", [])]
        data["pages"] = [
            PageReport(**{**p, "attempts": [Attempt(**a) for a in p.get("attempts", [])]})
            for p in data.get("pages", [])
        ]
        return cls(**data)
