"""Hard validation, completeness checks and plausibility warnings."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Iterable

from .config import (
    DECLINE_WARNING_FRACTION,
    LOCATIONS,
    RISE_WARNING_FACTOR,
    SOURCE_LABELS,
)
from .storage import row_key
from .weeks import parse_week, week_sunday


def finding(
    severity: str,
    check: str,
    message: str,
    *,
    location: str | None = None,
    week: str | None = None,
    observed: Any = None,
    expected: Any = None,
) -> dict[str, Any]:
    result = {"severity": severity, "check": check, "message": message}
    optional = {
        "location": location,
        "week": week,
        "observed": observed,
        "expected": expected,
    }
    result.update({key: value for key, value in optional.items() if value is not None})
    return result


def validate_source_labels(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in rows:
        code = row.get("source_region_code")
        observed = row.get("source_region_label")
        expected = SOURCE_LABELS.get(code)
        if expected and observed != expected:
            findings.append(
                finding(
                    "warning",
                    "source_label_changed",
                    f"Source label changed for region code {code}",
                    location=code,
                    week=row.get("source_year_week"),
                    observed=observed,
                    expected=expected,
                )
            )
    return findings


def validate_rows(
    rows: list[dict[str, Any]],
    requested_weeks: Iterable[str],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    requested = tuple(requested_weeks)
    required_regions = set(LOCATIONS)

    keys = [
        (row.get("source_region_code"), row.get("source_year_week")) for row in rows
    ]
    for key, count in Counter(keys).items():
        if count > 1:
            findings.append(
                finding(
                    "hard",
                    "duplicate_region_week",
                    "Duplicate source region-week combination",
                    location=key[0],
                    week=key[1],
                    observed=count,
                    expected=1,
                )
            )

    by_week: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        region = row.get("source_region_code")
        week = row.get("source_year_week")
        if region not in required_regions:
            findings.append(
                finding(
                    "hard",
                    "unexpected_region",
                    f"Unexpected source region {region!r}",
                    location=region,
                    week=week,
                )
            )
            continue
        try:
            parse_week(str(week))
        except (TypeError, ValueError) as exc:
            findings.append(
                finding("hard", "invalid_iso_week", str(exc), location=region, week=week)
            )
        by_week.setdefault(str(week), {})[str(region)] = row

        value = row.get("value")
        if row.get("status") != "available" or value is None:
            findings.append(
                finding(
                    "incomplete",
                    "missing_value",
                    "Source value is not available",
                    location=region,
                    week=week,
                    observed=row.get("status"),
                    expected="available",
                )
            )
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            findings.append(
                finding(
                    "hard",
                    "non_numeric_value",
                    "Source value is not numeric",
                    location=region,
                    week=week,
                    observed=value,
                )
            )
        elif value < 0 or int(value) != value:
            findings.append(
                finding(
                    "hard",
                    "invalid_count",
                    "Source value must be a non-negative integer",
                    location=region,
                    week=week,
                    observed=value,
                )
            )

    for week in requested:
        available_regions = set(by_week.get(week, {}))
        for missing_region in sorted(required_regions - available_regions):
            findings.append(
                finding(
                    "incomplete",
                    "missing_region_week",
                    "Required region is absent for the requested week",
                    location=missing_region,
                    week=week,
                )
            )

        week_rows = by_week.get(week, {})
        if all(
            region in week_rows and week_rows[region].get("status") == "available"
            for region in required_regions
        ):
            national = week_rows["00"]["value"]
            for region in ("12", "14"):
                regional = week_rows[region]["value"]
                if national < regional:
                    findings.append(
                        finding(
                            "hard",
                            "national_below_region",
                            "National count is below a regional count",
                            location=region,
                            week=week,
                            observed=national,
                            expected=f">= {regional}",
                        )
                    )

    existing_by_key = {row_key(row): row for row in existing}
    for row in rows:
        if row.get("status") != "available":
            continue
        code = row["source_region_code"]
        location = LOCATIONS[code][0]
        target_date = week_sunday(row["source_year_week"]).isoformat()
        previous = existing_by_key.get((location, target_date))
        if previous and str(previous["value"]) != str(int(row["value"])):
            findings.append(
                finding(
                    "hard",
                    "frozen_value_changed",
                    "A frozen hub value would be overwritten",
                    location=location,
                    week=row["source_year_week"],
                    observed=row["value"],
                    expected=previous["value"],
                )
            )

    findings.extend(validate_source_labels(rows))
    findings.extend(plausibility_warnings(rows, existing))
    return findings


def _numeric_value(row: dict[str, Any]) -> int | None:
    try:
        value = int(row["value"])
    except (KeyError, TypeError, ValueError):
        return None
    return value


def plausibility_warnings(
    candidates: list[dict[str, Any]], existing: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    history: dict[str, list[tuple[date, int]]] = {code: [] for code in LOCATIONS}
    location_to_source = {location: source for source, (location, _) in LOCATIONS.items()}
    for row in existing:
        source = location_to_source.get(row.get("location"))
        value = _numeric_value(row)
        if source and value is not None:
            history[source].append((date.fromisoformat(row["target_end_date"]), value))

    for row in sorted(
        candidates,
        key=lambda item: (week_sunday(item["source_year_week"]), item["source_region_code"]),
    ):
        if row.get("status") != "available":
            continue
        source = row["source_region_code"]
        value = _numeric_value(row)
        if value is None:
            continue
        target_date = week_sunday(row["source_year_week"])
        previous_values = [item for item in history[source] if item[0] < target_date]
        if previous_values:
            _, previous = max(previous_values, key=lambda item: item[0])
            if previous > 0 and value > RISE_WARNING_FACTOR * previous:
                warnings.append(
                    finding(
                        "warning",
                        "large_weekly_increase",
                        "Weekly value is more than five times the previous value",
                        location=LOCATIONS[source][0],
                        week=row["source_year_week"],
                        observed=value,
                        expected=f"<= {RISE_WARNING_FACTOR * previous}",
                    )
                )
            if previous > 0 and value < (1 - DECLINE_WARNING_FRACTION) * previous:
                warnings.append(
                    finding(
                        "warning",
                        "large_weekly_decline",
                        "Weekly value declined by more than 50 percent",
                        location=LOCATIONS[source][0],
                        week=row["source_year_week"],
                        observed=value,
                        expected=f">= {(1 - DECLINE_WARNING_FRACTION) * previous:g}",
                    )
                )
        history[source].append((target_date, value))
    return warnings
