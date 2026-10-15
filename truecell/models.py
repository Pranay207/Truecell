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

    def __post_init__(self) -> None:
        if not self.provenance:
            self.provenance = [[(self.page, i + 1)] for i in range(len(self.rows))]
        if not self.row_engines:
            self.row_engines = [self.engine] * len(self.rows)


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


@dataclass
class PageReport:
    page: int
    route: str
    engine: str = "none"
    confidence: float = 0
    seconds: float = 0
    attempts: list[Attempt] = field(default_factory=list)
    error: str = ""


@dataclass
class Result:
    source: str
    tables: list[Table] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    pages: list[PageReport] = field(default_factory=list)
    seconds: float = 0

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe audit records, omitting tuple-keyed OCR internals."""
        value = asdict(self)
        for table in value["tables"]:
            table.pop("cell_confidence", None)
        return value
