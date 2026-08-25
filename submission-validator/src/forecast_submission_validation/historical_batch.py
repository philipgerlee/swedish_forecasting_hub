"""Create and split one consolidated 2025/2026 historical submission."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from .config import COLUMNS, HORIZONS, LOCATIONS, TARGET
from .submission import validate_submission

MODEL_PATTERN = re.compile(r"^[A-Za-z0-9_+]+-[A-Za-z0-9_+]+$")


def load_reference_dates(manifest_path: Path) -> list[str]:
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "reference_date" not in (reader.fieldnames or []):
            raise ValueError("Manifest has no reference_date column")
        result = [row["reference_date"] for row in reader]
    if len(result) != 33 or len(set(result)) != 33:
        raise ValueError("Manifest must contain 33 unique reference dates")
    return result


def create_template(
    output_path: Path,
    *,
    reference_dates: list[str],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for reference_date in reference_dates:
            for location in LOCATIONS:
                for horizon in HORIZONS:
                    writer.writerow(
                        {
                            "reference_date": reference_date,
                            "target": TARGET,
                            "horizon": horizon,
                            "location": location,
                            "output_type": "mean",
                            "output_type_id": "",
                            "value": "",
                        }
                    )


def read_batch(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(
                f"Expected columns {list(COLUMNS)!r}; found {reader.fieldnames!r}"
            )
        return list(reader)


def split_and_validate(
    batch_path: Path,
    *,
    model_id: str,
    reference_dates: list[str],
    metadata_root: Path,
    schema_path: Path,
    output_root: Path,
) -> list[Path]:
    if not MODEL_PATTERN.fullmatch(model_id):
        raise ValueError("model_id must have the form team-model")
    rows = read_batch(batch_path)
    by_reference: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_reference[row["reference_date"].strip()].append(row)
    missing = sorted(set(reference_dates) - set(by_reference))
    unexpected = sorted(set(by_reference) - set(reference_dates))
    if missing or unexpected:
        raise ValueError(
            f"Historical reference dates do not match manifest; "
            f"missing={missing}, unexpected={unexpected}"
        )

    with tempfile.TemporaryDirectory() as temporary:
        temporary_model_root = Path(temporary) / model_id
        temporary_model_root.mkdir()
        temporary_paths: list[Path] = []
        reports = []
        for reference_date in reference_dates:
            path = temporary_model_root / f"{reference_date}-{model_id}.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(by_reference[reference_date])
            temporary_paths.append(path)
            reports.append(
                validate_submission(
                    path,
                    metadata_root=metadata_root,
                    schema_path=schema_path,
                )
            )

        invalid = [report for report in reports if report.status not in {"PASS", "WARN"}]
        if invalid:
            details = "; ".join(
                f"{Path(report.path).name}: {report.status}" for report in invalid
            )
            raise ValueError(f"Historical batch did not validate: {details}")

        destination = output_root / model_id
        destination.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for source in temporary_paths:
            target = destination / source.name
            shutil.copy2(source, target)
            written.append(target)
    return written


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("template", help="Create a 396-row batch template")
    template.add_argument("model_id")
    template.add_argument(
        "--manifest",
        type=Path,
        default=Path("retrospective-data/2025-2026/manifest.csv"),
    )
    template.add_argument("--output", type=Path)

    split = subparsers.add_parser("split", help="Validate and split a completed batch")
    split.add_argument("batch", type=Path)
    split.add_argument("model_id")
    split.add_argument(
        "--manifest",
        type=Path,
        default=Path("retrospective-data/2025-2026/manifest.csv"),
    )
    split.add_argument("--metadata-root", type=Path, default=Path("model-metadata"))
    split.add_argument(
        "--schema",
        type=Path,
        default=Path("hub-config/model-metadata-schema.json"),
    )
    split.add_argument("--output-root", type=Path, default=Path("model-output"))
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        reference_dates = load_reference_dates(args.manifest)
        if args.command == "template":
            if not MODEL_PATTERN.fullmatch(args.model_id):
                raise ValueError("model_id must have the form team-model")
            output = args.output or Path(
                f"historical-2025-2026-{args.model_id}.csv"
            )
            create_template(output, reference_dates=reference_dates)
            print(f"Wrote {len(reference_dates) * len(LOCATIONS) * len(HORIZONS)} rows to {output}")
            return
        paths = split_and_validate(
            args.batch,
            model_id=args.model_id,
            reference_dates=reference_dates,
            metadata_root=args.metadata_root,
            schema_path=args.schema,
            output_root=args.output_root,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Historical submission preparation failed: {exc}") from exc
    print(f"Validated and wrote {len(paths)} forecast files")


if __name__ == "__main__":
    main()
