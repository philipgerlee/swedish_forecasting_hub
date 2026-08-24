"""Command-line entry point for forecast-submission validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .submission import validate_submission


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("paths", nargs="+", type=Path, help="Forecast CSV file(s)")
    result.add_argument("--repo-root", type=Path, default=Path("."))
    result.add_argument("--metadata-root", type=Path)
    result.add_argument("--schema", type=Path)
    result.add_argument(
        "--submitted-at",
        help="ISO timestamp used for the live Sunday 23:59 deadline check",
    )
    result.add_argument(
        "--require-all-locations",
        action="store_true",
        help="Require SE, SE-M and SE-O even outside the historical period",
    )
    result.add_argument("--json-output", type=Path)
    return result


def main() -> None:
    args = parser().parse_args()
    repo_root = args.repo_root.resolve()
    metadata_root = (args.metadata_root or repo_root / "model-metadata").resolve()
    schema_path = (
        args.schema or repo_root / "hub-config" / "model-metadata-schema.json"
    ).resolve()
    reports = [
        validate_submission(
            path.resolve(),
            metadata_root=metadata_root,
            schema_path=schema_path,
            submitted_at=args.submitted_at,
            require_all_locations=args.require_all_locations,
        )
        for path in args.paths
    ]

    for report in reports:
        print(f"{report.status}: {report.path}")
        if report.accepted_locations:
            print(f"  accepted locations: {', '.join(report.accepted_locations)}")
        if report.rejected_locations:
            print(f"  rejected locations: {', '.join(report.rejected_locations)}")
        for finding in report.findings:
            context = []
            if finding.location is not None:
                context.append(f"location={finding.location}")
            if finding.row is not None:
                context.append(f"row={finding.row}")
            suffix = f" ({', '.join(context)})" if context else ""
            print(
                f"  {finding.severity.upper()} {finding.check}: "
                f"{finding.message}{suffix}"
            )

    if args.json_output:
        args.json_output.write_text(
            json.dumps([report.as_dict() for report in reports], indent=2) + "\n",
            encoding="utf-8",
        )
    raise SystemExit(1 if any(report.failed for report in reports) else 0)


if __name__ == "__main__":
    main()
