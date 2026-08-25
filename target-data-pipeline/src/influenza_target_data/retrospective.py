"""Build fixed retrospective round inputs and evaluation outcomes for 2025/2026."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from .config import API_URL, LOCATIONS, OUTPUT_COLUMNS, TIME_DIMENSION
from .fetch import FolkhalsodataClient, SourceError
from .transform import TransformError, transform_dataset
from .weeks import parse_week, week_sunday

ROUND_START = date.fromisocalendar(2025, 40, 7)
ROUND_END = date.fromisocalendar(2026, 20, 7)
OUTCOME_END = date.fromisocalendar(2026, 23, 7)
OUTCOME_START_WEEK = "2025W40"
MANIFEST_COLUMNS = (
    "round_number",
    "reference_date",
    "data_cutoff",
    "input_file",
    "expected_output_file",
    "data_version",
)


def weekly_dates(start: date, end: date) -> list[date]:
    if start.weekday() != 6 or end.weekday() != 6:
        raise ValueError("Weekly date ranges must start and end on Sunday")
    if end < start:
        raise ValueError("Weekly date range ends before it starts")
    result: list[date] = []
    cursor = start
    while cursor <= end:
        result.append(cursor)
        cursor += timedelta(days=7)
    return result


def round_reference_dates() -> list[date]:
    return weekly_dates(ROUND_START, ROUND_END)


def _metadata_weeks(metadata: dict[str, Any]) -> list[str]:
    for variable in metadata.get("variables", []):
        if variable.get("code") == TIME_DIMENSION:
            values = variable.get("values")
            if isinstance(values, list) and all(isinstance(value, str) for value in values):
                return values
    raise SourceError(f"Metadata has no valid {TIME_DIMENSION!r} values")


def source_weeks_through(metadata: dict[str, Any], cutoff: date) -> list[str]:
    weeks = _metadata_weeks(metadata)
    result = [week for week in weeks if week_sunday(week) <= cutoff]
    return sorted(result, key=week_sunday)


def canonical_rows(
    source_rows: Iterable[dict[str, Any]],
    *,
    data_version: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in source_rows:
        source_code = row["source_region_code"]
        if source_code not in LOCATIONS:
            continue
        source_week = row["source_year_week"]
        year, week = parse_week(source_week)
        location, location_name = LOCATIONS[source_code]
        result.append(
            {
                "location": location,
                "location_name": location_name,
                "year": year,
                "week": week,
                "target_end_date": week_sunday(source_week).isoformat(),
                "value": row["value"],
                "status": row["status"],
                "release_status": "historical",
                "data_version": data_version,
                "source_region_code": source_code,
                "source_year_week": source_week,
                "official_release_time": "",
            }
        )
    return sorted(
        result,
        key=lambda row: (row["target_end_date"], row["source_region_code"]),
    )


def validate_canonical_rows(rows: list[dict[str, Any]], weeks: Iterable[str]) -> None:
    counts = Counter(row["source_year_week"] for row in rows)
    invalid = {week: counts[week] for week in weeks if counts[week] != len(LOCATIONS)}
    if invalid:
        raise ValueError(f"Expected {len(LOCATIONS)} locations per week: {invalid}")


def write_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in OUTPUT_COLUMNS})


def write_manifest(path: Path, data_version: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for number, reference_date in enumerate(round_reference_dates(), start=1):
        records.append(
            {
                "round_number": str(number),
                "reference_date": reference_date.isoformat(),
                "data_cutoff": (reference_date - timedelta(days=7)).isoformat(),
                "input_file": f"rounds/{reference_date.isoformat()}.csv",
                "expected_output_file": (
                    f"{reference_date.isoformat()}-<model_id>.csv"
                ),
                "data_version": data_version,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    return records


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
            raise ValueError(f"Unexpected columns in {path}: {reader.fieldnames!r}")
        return list(reader)


def verify_artifacts(output_root: Path) -> None:
    manifest_path = output_root / "manifest.csv"
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != MANIFEST_COLUMNS:
            raise ValueError(f"Unexpected manifest columns: {reader.fieldnames!r}")
        manifest = list(reader)
    expected_rounds = round_reference_dates()
    if len(manifest) != len(expected_rounds):
        raise ValueError(
            f"Expected {len(expected_rounds)} manifest rounds, received {len(manifest)}"
        )
    for number, (record, expected_reference) in enumerate(
        zip(manifest, expected_rounds), start=1
    ):
        if record["round_number"] != str(number):
            raise ValueError(f"Unexpected round number in manifest row {number}")
        if record["reference_date"] != expected_reference.isoformat():
            raise ValueError(f"Unexpected reference_date in manifest row {number}")
        expected_cutoff = expected_reference - timedelta(days=7)
        if record["data_cutoff"] != expected_cutoff.isoformat():
            raise ValueError(f"Unexpected data_cutoff in manifest row {number}")
        rows = read_rows(output_root / record["input_file"])
        if not rows:
            raise ValueError(f"Snapshot is empty: {record['input_file']}")
        if max(row["target_end_date"] for row in rows) != record["data_cutoff"]:
            raise ValueError(f"Snapshot cutoff mismatch: {record['input_file']}")
        weeks = sorted({row["source_year_week"] for row in rows}, key=week_sunday)
        validate_canonical_rows(rows, weeks)

    outcomes = read_rows(output_root / "final-outcomes.csv")
    outcome_weeks = sorted(
        {row["source_year_week"] for row in outcomes}, key=week_sunday
    )
    expected_outcome_dates = weekly_dates(
        week_sunday(OUTCOME_START_WEEK), OUTCOME_END
    )
    if [week_sunday(week) for week in outcome_weeks] != expected_outcome_dates:
        raise ValueError("Final outcome weeks do not cover week 40 through week 23")
    validate_canonical_rows(outcomes, outcome_weeks)


def build(output_root: Path, *, data_version: str, api_url: str = API_URL) -> None:
    client = FolkhalsodataClient(api_url)
    metadata = client.metadata()
    requested_weeks = source_weeks_through(metadata, OUTCOME_END)
    source = client.fetch(requested_weeks)
    if source.unavailable_weeks:
        raise SourceError(
            f"Source did not return metadata for {list(source.unavailable_weeks)!r}"
        )
    rows = canonical_rows(transform_dataset(source.dataset), data_version=data_version)
    validate_canonical_rows(rows, requested_weeks)

    manifest = write_manifest(output_root / "manifest.csv", data_version)
    for record in manifest:
        cutoff = date.fromisoformat(record["data_cutoff"])
        snapshot = [
            row for row in rows if date.fromisoformat(row["target_end_date"]) <= cutoff
        ]
        write_rows(output_root / record["input_file"], snapshot)

    outcome_start = week_sunday(OUTCOME_START_WEEK)
    outcomes = [
        row
        for row in rows
        if outcome_start <= date.fromisoformat(row["target_end_date"]) <= OUTCOME_END
    ]
    outcome_weeks = sorted({row["source_year_week"] for row in outcomes}, key=week_sunday)
    validate_canonical_rows(outcomes, outcome_weeks)
    expected_outcome_weeks = weekly_dates(outcome_start, OUTCOME_END)
    if len(outcome_weeks) != len(expected_outcome_weeks):
        raise ValueError(
            f"Expected {len(expected_outcome_weeks)} outcome weeks, "
            f"received {len(outcome_weeks)}"
        )
    write_rows(output_root / "final-outcomes.csv", outcomes)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--output-root",
        type=Path,
        default=Path("retrospective-data/2025-2026"),
    )
    result.add_argument(
        "--data-version",
        help="Fixed ISO timestamp recorded in every generated row and manifest entry",
    )
    result.add_argument("--api-url", default=API_URL)
    result.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify committed artifacts without contacting Folkhälsodata",
    )
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        if args.verify_only:
            verify_artifacts(args.output_root)
            print(
                f"Verified {len(round_reference_dates())} retrospective rounds "
                f"in {args.output_root}"
            )
            return
        if not args.data_version:
            raise ValueError("--data-version is required when building artifacts")
        build(args.output_root, data_version=args.data_version, api_url=args.api_url)
    except (OSError, SourceError, TransformError, ValueError) as exc:
        raise SystemExit(f"Retrospective data build failed: {exc}") from exc
    print(f"Wrote {len(round_reference_dates())} retrospective rounds to {args.output_root}")


if __name__ == "__main__":
    main()
