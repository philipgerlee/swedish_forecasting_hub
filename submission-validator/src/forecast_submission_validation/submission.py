"""Validate one point-forecast CSV and its model metadata."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import (
    COLUMNS,
    HIGH_VALUE_WARNING,
    HISTORICAL_END,
    HISTORICAL_START,
    HORIZONS,
    LIVE_END,
    LIVE_START,
    LOCATIONS,
    OUTPUT_TYPE,
    TARGET,
)
from .metadata import MetadataError, load_metadata
from .report import ValidationReport

FILE_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-"
    r"(?P<model>[A-Za-z0-9_+]+-[A-Za-z0-9_+]+)\.csv$"
)
STOCKHOLM = ZoneInfo("Europe/Stockholm")


def _parse_submitted_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("submission timestamp must include a timezone")
    return parsed


def _round_kind(reference_date: date) -> str | None:
    if HISTORICAL_START <= reference_date <= HISTORICAL_END:
        return "historical"
    if LIVE_START <= reference_date <= LIVE_END:
        return "live"
    return None


def validate_submission(
    path: Path,
    *,
    metadata_root: Path,
    schema_path: Path,
    submitted_at: str | None = None,
    require_all_locations: bool = False,
) -> ValidationReport:
    report = ValidationReport(path=str(path))
    match = FILE_PATTERN.fullmatch(path.name)
    if not match:
        report.add(
            "error",
            "filename",
            "Expected YYYY-MM-DD-<team>-<model>.csv",
        )
        return report

    filename_date_text = match.group("date")
    model_id = match.group("model")
    report.model_id = model_id
    if path.parent.name != model_id:
        report.add(
            "error",
            "directory_model_id",
            f"Parent directory {path.parent.name!r} must equal model_id {model_id!r}",
        )

    try:
        filename_date = date.fromisoformat(filename_date_text)
    except ValueError:
        report.add("error", "reference_date", "Filename contains an invalid date")
        return report
    report.reference_date = filename_date_text
    if filename_date.weekday() != 6:
        report.add("error", "reference_date", "reference_date must be a Sunday")

    round_kind = _round_kind(filename_date)
    if round_kind is None:
        report.add(
            "error",
            "round",
            "reference_date is outside the 2025/2026 historical and 2026/2027 live rounds",
        )
    if round_kind == "historical":
        require_all_locations = True

    if submitted_at and round_kind == "live":
        try:
            submitted = _parse_submitted_at(submitted_at).astimezone(STOCKHOLM)
            deadline = datetime.combine(filename_date, time(23, 59, 59), STOCKHOLM)
            if submitted > deadline:
                report.add(
                    "error",
                    "deadline",
                    f"Submission time {submitted.isoformat()} is after {deadline.isoformat()}",
                )
        except ValueError as exc:
            report.add("error", "deadline", str(exc))

    try:
        load_metadata(model_id, metadata_root, schema_path)
    except (MetadataError, OSError, json.JSONDecodeError) as exc:
        report.add("error", "metadata", str(exc))

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                report.add(
                    "error",
                    "columns",
                    f"Expected columns {list(COLUMNS)!r}; found {reader.fieldnames!r}",
                )
                return _finish(report, set(), set())
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        report.add("error", "csv", f"Could not read CSV: {exc}")
        return report

    if not rows:
        report.add("error", "rows", "Submission contains no forecast rows")
        return report

    by_location: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        location = (row.get("location") or "").strip()
        by_location[location].append((row_number, row))

    accepted: set[str] = set()
    rejected: set[str] = set()
    for location, location_rows in by_location.items():
        errors_before = len(
            [
                finding
                for finding in report.findings
                if finding.severity == "error" and finding.location == location
            ]
        )
        if location not in LOCATIONS:
            report.add(
                "error",
                "location",
                f"Unsupported location {location!r}",
                location=location or "<empty>",
            )
            rejected.add(location or "<empty>")
            continue

        horizons: list[int] = []
        for row_number, row in location_rows:
            if any(value is None for value in row.values()):
                report.add(
                    "error",
                    "row_shape",
                    "Row has too many or too few fields",
                    location=location,
                    row=row_number,
                )
                continue
            if row["reference_date"].strip() != filename_date_text:
                report.add(
                    "error",
                    "reference_date",
                    "Row reference_date does not match the filename",
                    location=location,
                    row=row_number,
                )
            if row["target"].strip() != TARGET:
                report.add(
                    "error",
                    "target",
                    f"target must be {TARGET!r}",
                    location=location,
                    row=row_number,
                )
            if row["output_type"].strip() != OUTPUT_TYPE:
                report.add(
                    "error",
                    "output_type",
                    "output_type must be 'mean'",
                    location=location,
                    row=row_number,
                )
            if row["output_type_id"].strip().upper() not in {"", "NA", "N/A"}:
                report.add(
                    "error",
                    "output_type_id",
                    "output_type_id must be empty or NA for mean forecasts",
                    location=location,
                    row=row_number,
                )
            try:
                horizon = int(row["horizon"])
                if str(horizon) != row["horizon"].strip() or horizon not in HORIZONS:
                    raise ValueError
                horizons.append(horizon)
            except ValueError:
                report.add(
                    "error",
                    "horizon",
                    "horizon must be one of 0, 1, 2, 3",
                    location=location,
                    row=row_number,
                )
            try:
                value = float(row["value"])
                if not math.isfinite(value) or value < 0:
                    raise ValueError
                if value > HIGH_VALUE_WARNING:
                    report.add(
                        "warning",
                        "high_value",
                        f"Technically valid value {value:g} requires manual review",
                        location=location,
                        row=row_number,
                    )
            except ValueError:
                report.add(
                    "error",
                    "value",
                    "value must be numeric, finite and at least zero",
                    location=location,
                    row=row_number,
                )

        duplicates = sorted(h for h, count in Counter(horizons).items() if count > 1)
        if duplicates:
            report.add(
                "error",
                "duplicate_horizon",
                f"Duplicate horizon(s): {duplicates}",
                location=location,
            )
        missing = sorted(set(HORIZONS) - set(horizons))
        if missing:
            report.add(
                "error",
                "missing_horizon",
                f"Missing horizon(s): {missing}",
                location=location,
            )

        errors_after = len(
            [
                finding
                for finding in report.findings
                if finding.severity == "error" and finding.location == location
            ]
        )
        if errors_after == errors_before:
            accepted.add(location)
        else:
            rejected.add(location)

    if require_all_locations:
        unavailable_locations = sorted(set(LOCATIONS) - accepted)
        if unavailable_locations:
            report.add(
                "error",
                "missing_location",
                "All locations must be present and valid; "
                f"unavailable {unavailable_locations}",
            )

    return _finish(report, accepted, rejected)


def _finish(
    report: ValidationReport,
    accepted: set[str],
    rejected: set[str],
) -> ValidationReport:
    report.accepted_locations = sorted(accepted)
    report.rejected_locations = sorted(rejected)
    file_errors = [
        finding
        for finding in report.findings
        if finding.severity == "error" and finding.location is None
    ]
    if file_errors or not accepted:
        report.status = "FAIL"
    elif rejected:
        report.status = "PARTIAL"
    elif any(finding.severity == "warning" for finding in report.findings):
        report.status = "WARN"
    else:
        report.status = "PASS"
    return report
