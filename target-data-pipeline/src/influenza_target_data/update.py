"""Command-line orchestration for one target-data update candidate."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import API_URL, LOCATIONS
from .fetch import FolkhalsodataClient, SourceError, validate_metadata
from .report import write_markdown, write_report
from .storage import StorageError, load_rows, new_rows_only, write_rows_atomic
from .transform import TransformError, transform_dataset
from .validate import finding, validate_rows
from .weeks import parse_week, previous_week, season_weeks_through, week_sunday


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _github_outputs(values: dict[str, Any]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def _published_weeks(rows: list[dict[str, str]]) -> set[str]:
    counts: dict[str, set[str]] = {}
    for row in rows:
        counts.setdefault(row["source_year_week"], set()).add(row["source_region_code"])
    required = set(LOCATIONS)
    return {week for week, regions in counts.items() if regions == required}


def target_weeks(
    existing: list[dict[str, str]],
    now: datetime,
    explicit: list[str] | None = None,
) -> list[str]:
    if explicit:
        for week in explicit:
            parse_week(week)
        return list(dict.fromkeys(explicit))
    latest = previous_week(now)
    expected = season_weeks_through(latest)
    published = _published_weeks(existing)
    return [week for week in expected if week not in published]


def _candidate_rows(
    source_rows: list[dict[str, Any]],
    now: datetime,
    latest_expected_week: str,
) -> list[dict[str, Any]]:
    timestamp = _utc_text(now)
    candidates: list[dict[str, Any]] = []
    for row in source_rows:
        source_code = row["source_region_code"]
        source_week = row["source_year_week"]
        if source_code not in LOCATIONS:
            continue
        year, week = parse_week(source_week)
        location, location_name = LOCATIONS[source_code]
        candidates.append(
            {
                **row,
                "location": location,
                "location_name": location_name,
                "year": year,
                "week": week,
                "target_end_date": week_sunday(source_week).isoformat(),
                "release_status": (
                    "on_time" if source_week == latest_expected_week else "delayed_release"
                ),
                "data_version": timestamp,
                "official_release_time": timestamp,
            }
        )
    return candidates


def _base_report(now: datetime, requested: list[str], api_url: str) -> dict[str, Any]:
    return {
        "generated_at": _utc_text(now),
        "source_url": api_url,
        "requested_weeks": requested,
        "status": "UNKNOWN",
        "new_rows": 0,
        "warning_count": 0,
        "hard_failure_count": 0,
        "incomplete_count": 0,
        "findings": [],
    }


def run(args: argparse.Namespace) -> int:
    now = (
        datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        if args.now
        else datetime.now(timezone.utc)
    )
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    output_path = Path(args.output)
    report_path = Path(args.report)
    summary_path = Path(args.summary)

    requested: list[str] = []
    report = _base_report(now, requested, args.api_url)
    try:
        existing = load_rows(output_path)
        requested = target_weeks(existing, now, args.target_week)
        report["requested_weeks"] = requested
        if not requested:
            report["status"] = "NO_UPDATE"
            write_report(report_path, report)
            write_markdown(summary_path, report)
            _github_outputs(
                {"changed": False, "status": "no_update", "warnings": False}
            )
            print("No unpublished in-season target weeks.")
            return 0

        client = FolkhalsodataClient(args.api_url)
        source = client.fetch(requested)
        report["source_metadata_title"] = source.metadata.get("title")
        report["source_fetched_at"] = _utc_text(source.fetched_at)
        report["source_available_weeks"] = list(source.available_weeks)
        report["source_unavailable_weeks"] = list(source.unavailable_weeks)
        report["findings"].extend(validate_metadata(source.metadata))
        for week in source.unavailable_weeks:
            report["findings"].append(
                finding(
                    "incomplete",
                    "target_week_not_published",
                    "The requested target week is not yet present in source metadata",
                    week=week,
                )
            )

        raw_rows = transform_dataset(source.dataset)
        latest_expected = previous_week(now)
        candidates = _candidate_rows(raw_rows, now, latest_expected)
        report["findings"].extend(validate_rows(candidates, requested, existing))

        hard = [item for item in report["findings"] if item["severity"] == "hard"]
        incomplete = [
            item for item in report["findings"] if item["severity"] == "incomplete"
        ]
        warnings = [
            item for item in report["findings"] if item["severity"] == "warning"
        ]
        report["hard_failure_count"] = len(hard)
        report["incomplete_count"] = len(incomplete)
        report["warning_count"] = len(warnings)

        if hard:
            report["status"] = "FAIL"
            exit_code = 1
        elif incomplete:
            report["status"] = "INCOMPLETE"
            exit_code = 0
        else:
            additions = new_rows_only(existing, candidates)
            report["new_rows"] = len(additions)
            report["status"] = "WARN" if warnings else "PASS"
            if additions and not args.dry_run:
                write_rows_atomic(output_path, [*existing, *additions])
            exit_code = 0

        write_report(report_path, report)
        write_markdown(summary_path, report)
        changed = bool(report["new_rows"] and not args.dry_run)
        _github_outputs(
            {
                "changed": changed,
                "status": report["status"].lower(),
                "warnings": bool(warnings),
                "latest_target_week": requested[-1],
                "target_weeks": ",".join(requested),
            }
        )
        print(
            f"Validation status {report['status']}; "
            f"{report['new_rows']} new rows; {len(warnings)} warnings."
        )
        return exit_code
    except (SourceError, StorageError, TransformError, ValueError) as exc:
        report["status"] = "FAIL"
        report["hard_failure_count"] = 1
        report["findings"].append(
            finding("hard", "pipeline_exception", str(exc))
        )
        write_report(report_path, report)
        write_markdown(summary_path, report)
        _github_outputs(
            {
                "changed": False,
                "status": "fail",
                "warnings": False,
                "latest_target_week": requested[-1] if requested else "unknown",
                "target_weeks": ",".join(requested),
            }
        )
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--target-week",
        action="append",
        help="Explicit ISO target week (YYYYWww); may be repeated",
    )
    result.add_argument("--output", default="target-data/time-series.csv")
    result.add_argument("--report", default="validation-report.json")
    result.add_argument("--summary", default="validation-summary.md")
    result.add_argument("--api-url", default=API_URL)
    result.add_argument("--dry-run", action="store_true")
    result.add_argument(
        "--now",
        help=argparse.SUPPRESS,
    )
    return result


def main() -> None:
    raise SystemExit(run(parser().parse_args()))


if __name__ == "__main__":
    main()
