"""Build a rolling-origin probabilistic normal MA3 baseline."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import NormalDist
from typing import Any

from .qra import QUANTILES

MODEL_ID = "hub-normalma3"
TARGET = "weekly incident influenza cases"
MEAN_WINDOW_WEEKS = 3
MIN_RESIDUAL_SAMPLES = 8
BASELINE_COLUMNS = (
    "reference_date",
    "target_end_date",
    "target",
    "horizon",
    "location",
    "location_name",
    "output_type",
    "output_type_id",
    "value",
    "distribution",
    "mean",
    "standard_deviation",
    "mean_window_weeks",
    "training_sample_count",
    "training_last_target_end_date",
    "outcome_data_version",
)
HUBVERSE_COLUMNS = (
    "reference_date",
    "target_end_date",
    "target",
    "horizon",
    "location",
    "output_type",
    "output_type_id",
    "value",
)
REQUIRED_MANIFEST_COLUMNS = (
    "reference_date",
    "data_cutoff",
    "input_file",
    "data_version",
)
REQUIRED_ROUND_COLUMNS = (
    "location",
    "location_name",
    "target_end_date",
    "value",
)


def _format_number(value: float) -> str:
    return format(value, ".12g")


def _read_csv(path: Path, required: tuple[str, ...], label: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(required) - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"{label} is missing columns: {missing}")
        return list(reader)


def _observations(
    rows: list[dict[str, str]], cutoff: date
) -> tuple[dict[str, dict[date, float]], dict[str, str]]:
    by_location: dict[str, dict[date, float]] = defaultdict(dict)
    names: dict[str, str] = {}
    for row_number, row in enumerate(rows, start=2):
        location = row["location"].strip()
        location_name = row["location_name"].strip()
        try:
            target_date = date.fromisoformat(row["target_end_date"].strip())
        except ValueError as exc:
            raise ValueError(f"Invalid target_end_date in round row {row_number}") from exc
        raw_value = row["value"].strip()
        if not raw_value or target_date > cutoff:
            continue
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Non-numeric value in round row {row_number}") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid value in round row {row_number}")
        if location in names and names[location] != location_name:
            raise ValueError(f"Location name changes within round data: {location}")
        if target_date in by_location[location]:
            raise ValueError(f"Duplicate observation for {location}, {target_date}")
        names[location] = location_name
        by_location[location][target_date] = value
    return dict(by_location), names


def _mean_for_origin(series: dict[date, float], origin: date) -> float | None:
    dates = [origin - timedelta(weeks=offset) for offset in range(1, 4)]
    if not all(target_date in series for target_date in dates):
        return None
    return sum(series[target_date] for target_date in dates) / MEAN_WINDOW_WEEKS


def _historical_errors(
    series: dict[date, float], horizon: int, cutoff: date
) -> list[tuple[date, float]]:
    result = []
    for target_date in sorted(series):
        if target_date > cutoff:
            continue
        origin = target_date - timedelta(weeks=horizon)
        prediction = _mean_for_origin(series, origin)
        if prediction is not None:
            result.append((target_date, series[target_date] - prediction))
    return result


def generate_round(
    rows: list[dict[str, str]],
    *,
    reference_date: date,
    data_cutoff: date,
    data_version: str,
    minimum_residual_samples: int = MIN_RESIDUAL_SAMPLES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if data_cutoff != reference_date - timedelta(weeks=1):
        raise ValueError("Baseline data cutoff must be one week before reference_date")
    if minimum_residual_samples < 2:
        raise ValueError("minimum_residual_samples must be at least two")
    series_by_location, names = _observations(rows, data_cutoff)
    forecasts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for location, series in sorted(series_by_location.items()):
        mean = _mean_for_origin(series, reference_date)
        if mean is None:
            skipped.append(
                {
                    "reference_date": reference_date.isoformat(),
                    "location": location,
                    "horizon": None,
                    "reason": "three_consecutive_recent_observations_unavailable",
                }
            )
            continue
        for horizon in range(4):
            errors = _historical_errors(series, horizon, data_cutoff)
            if len(errors) < minimum_residual_samples:
                skipped.append(
                    {
                        "reference_date": reference_date.isoformat(),
                        "location": location,
                        "horizon": horizon,
                        "available_training_samples": len(errors),
                        "required_training_samples": minimum_residual_samples,
                        "reason": "insufficient_historical_residuals",
                    }
                )
                continue
            standard_deviation = math.sqrt(
                sum(error * error for _, error in errors) / len(errors)
            )
            target_end_date = reference_date + timedelta(weeks=horizon)
            for quantile in QUANTILES:
                value = max(
                    0.0,
                    mean + NormalDist().inv_cdf(quantile) * standard_deviation,
                )
                forecasts.append(
                    {
                        "reference_date": reference_date.isoformat(),
                        "target_end_date": target_end_date.isoformat(),
                        "target": TARGET,
                        "horizon": horizon,
                        "location": location,
                        "location_name": names[location],
                        "output_type": "quantile",
                        "output_type_id": format(quantile, "g"),
                        "value": _format_number(value),
                        "distribution": "normal_quantiles_clipped_at_zero",
                        "mean": _format_number(mean),
                        "standard_deviation": _format_number(standard_deviation),
                        "mean_window_weeks": MEAN_WINDOW_WEEKS,
                        "training_sample_count": len(errors),
                        "training_last_target_end_date": errors[-1][0].isoformat(),
                        "outcome_data_version": data_version,
                    }
                )
    return forecasts, skipped


def generate_baseline(
    manifest_path: Path,
    *,
    minimum_residual_samples: int = MIN_RESIDUAL_SAMPLES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = _read_csv(manifest_path, REQUIRED_MANIFEST_COLUMNS, "Manifest")
    forecasts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row_number, row in enumerate(manifest, start=2):
        try:
            reference_date = date.fromisoformat(row["reference_date"])
            data_cutoff = date.fromisoformat(row["data_cutoff"])
        except ValueError as exc:
            raise ValueError(f"Invalid date in manifest row {row_number}") from exc
        input_path = manifest_path.parent / row["input_file"]
        round_rows = _read_csv(input_path, REQUIRED_ROUND_COLUMNS, "Round data")
        round_forecasts, round_skipped = generate_round(
            round_rows,
            reference_date=reference_date,
            data_cutoff=data_cutoff,
            data_version=row["data_version"].strip(),
            minimum_residual_samples=minimum_residual_samples,
        )
        forecasts.extend(round_forecasts)
        skipped.extend(round_skipped)
    return forecasts, skipped


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_hubverse_files(root: Path, rows: list[dict[str, Any]]) -> list[Path]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["reference_date"])].append(
            {column: row[column] for column in HUBVERSE_COLUMNS}
        )
    paths = []
    for reference_date, group in sorted(grouped.items()):
        path = root / MODEL_ID / f"{reference_date}-{MODEL_ID}.csv"
        write_csv(path, HUBVERSE_COLUMNS, group)
        paths.append(path)
    return paths


def write_report(
    path: Path,
    forecasts: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> None:
    training_counts = [int(row["training_sample_count"]) for row in forecasts]
    report = {
        "status": "complete",
        "model_id": MODEL_ID,
        "method": "normal predictive distribution around a three-week moving average",
        "mean": "arithmetic mean of the three latest consecutive available weekly observations",
        "uncertainty": "horizon- and location-specific historical RMSE around zero",
        "temporal_training_rule": "historical target_end_date <= reference_date - 7 days",
        "distribution": "normal with negative quantiles clipped at zero",
        "quantiles": list(QUANTILES),
        "minimum_residual_samples": MIN_RESIDUAL_SAMPLES,
        "forecast_row_count": len(forecasts),
        "forecast_task_count": len(forecasts) // len(QUANTILES),
        "skipped_task_count": len(skipped),
        "minimum_training_sample_count": min(training_counts) if training_counts else None,
        "maximum_training_sample_count": max(training_counts) if training_counts else None,
        "dashboard_compatible_export_available": True,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--manifest",
        type=Path,
        default=Path("retrospective-data/2025-2026/manifest.csv"),
    )
    result.add_argument(
        "--output-root",
        type=Path,
        default=Path("evaluation-output/2025-2026"),
    )
    result.add_argument(
        "--hubverse-output-root",
        type=Path,
        help="Optional root for per-round Hubverse dashboard model-output files",
    )
    result.add_argument("--allow-empty", action="store_true")
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        forecasts, skipped = generate_baseline(args.manifest)
        if not forecasts and not args.allow_empty:
            raise ValueError("Baseline generation produced no forecasts")
        write_csv(
            args.output_root / "normal-ma3-baseline-forecasts.csv",
            BASELINE_COLUMNS,
            forecasts,
        )
        write_report(
            args.output_root / "normal-ma3-baseline-report.json",
            forecasts,
            skipped,
        )
        skipped_path = args.output_root / "normal-ma3-baseline-skipped-tasks.json"
        skipped_path.write_text(json.dumps(skipped, indent=2) + "\n", encoding="utf-8")
        hubverse_paths = (
            write_hubverse_files(args.hubverse_output_root, forecasts)
            if args.hubverse_output_root
            else []
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Probabilistic baseline build failed: {exc}") from exc
    print(f"Wrote {len(forecasts)} probabilistic baseline quantile rows")
    print(f"Skipped {len(skipped)} tasks")
    if hubverse_paths:
        print(f"Wrote {len(hubverse_paths)} Hubverse dashboard forecast files")


if __name__ == "__main__":
    main()
