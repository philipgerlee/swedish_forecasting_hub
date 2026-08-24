"""Structured validation findings and summaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Finding:
    severity: str
    check: str
    message: str
    location: str | None = None
    row: int | None = None


@dataclass
class ValidationReport:
    path: str
    model_id: str | None = None
    reference_date: str | None = None
    status: str = "FAIL"
    accepted_locations: list[str] = field(default_factory=list)
    rejected_locations: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def add(
        self,
        severity: str,
        check: str,
        message: str,
        *,
        location: str | None = None,
        row: int | None = None,
    ) -> None:
        self.findings.append(Finding(severity, check, message, location, row))

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["path"] = str(Path(self.path))
        return result

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"
