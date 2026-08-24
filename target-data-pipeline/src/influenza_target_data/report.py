"""Validation report serialization and human-readable summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def markdown(report: dict[str, Any]) -> str:
    status = report.get("status", "UNKNOWN")
    weeks = ", ".join(report.get("requested_weeks", [])) or "none"
    lines = [
        "## Influenza target-data validation",
        "",
        f"- **Status:** {status}",
        f"- **Target weeks:** {weeks}",
        f"- **New rows:** {report.get('new_rows', 0)}",
        f"- **Warnings:** {report.get('warning_count', 0)}",
        f"- **Generated:** {report.get('generated_at', 'unknown')}",
    ]
    findings = report.get("findings", [])
    if findings:
        lines.extend(["", "### Findings", ""])
        for item in findings:
            context = " / ".join(
                str(item[key]) for key in ("location", "week") if item.get(key)
            )
            suffix = f" ({context})" if context else ""
            lines.append(
                f"- **{item.get('severity', 'unknown').upper()}** "
                f"`{item.get('check', 'unknown')}`: {item.get('message', '')}{suffix}"
            )
    return "\n".join(lines) + "\n"


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown(report), encoding="utf-8")
