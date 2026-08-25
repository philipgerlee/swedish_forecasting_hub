"""Calculate retrospective MAE, bias and RMSE for individual point forecasts."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

REQUIRED_MATCHED_COLUMNS = (
    "model_id",
    "round_number",
    "reference_date",
    "target_end_date",
    "target",
    "horizon",
    "location",
    "location_name",
    "output_type",
    "forecast_value",
    "observed_value",
    "outcome_data_version",
    "forecast_file",
)
POINT_ERROR_COLUMNS = (
    "model_id",
    "round_number",
    "reference_date",
    "target_end_date",
    "target",
    "horizon",
    "location",
    "location_name",
    "forecast_kind",
    "forecast_value",
    "observed_value",
    "error",
    "absolute_error",
    "squared_error",
    "outcome_data_version",
    "forecast_file",
)
HORIZON_METRIC_COLUMNS = (
    "model_id",
    "location",
    "location_name",
    "horizon",
    "forecast_kind",
    "n",
    "mae",
    "bias",
    "rmse",
    "first_reference_date",
    "last_reference_date",
    "outcome_data_version",
)
KIND_METRIC_COLUMNS = (
    "model_id",
    "location",
    "location_name",
    "forecast_kind",
    "n",
    "mae",
    "bias",
    "rmse",
    "first_reference_date",
    "last_reference_date",
    "outcome_data_version",
)


def _finite_nonnegative(value: str, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} is not numeric: {value!r}") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{context} must be finite and at least zero")
    return result


def _format_number(value: float) -> str:
    return format(value, ".12g")


def read_matches(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(REQUIRED_MATCHED_COLUMNS) - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"Matched forecast data is missing columns: {missing}")
        return list(reader)


def point_errors(rows: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, int]] = set()
    observed: dict[tuple[str, str], tuple[float, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        context = f"matched row {row_number}"
        model_id = row["model_id"].strip()
        location = row["location"].strip()
        reference_date = row["reference_date"].strip()
        target_end_date = row["target_end_date"].strip()
        if not model_id or not location or not reference_date or not target_end_date:
            raise ValueError(f"Identifiers must not be empty in {context}")
        try:
            horizon = int(row["horizon"])
            round_number = int(row["round_number"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid horizon or round number in {context}") from exc
        if horizon not in (0, 1, 2, 3):
            raise ValueError(f"Unsupported horizon in {context}: {horizon}")
        if row["output_type"] != "mean":
            raise ValueError(f"Only mean forecasts can be point-scored: {context}")
        forecast_value = _finite_nonnegative(
            row["forecast_value"], f"Forecast value in {context}"
        )
        observed_value = _finite_nonnegative(
            row["observed_value"], f"Observed value in {context}"
        )
        unique_key = (model_id, reference_date, location, horizon)
        if unique_key in seen:
            raise ValueError(f"Duplicate matched forecast: {unique_key}")
        seen.add(unique_key)
        outcome_key = (location, target_end_date)
        outcome_identity = (observed_value, row["outcome_data_version"])
        if outcome_key in observed and observed[outcome_key] != outcome_identity:
            raise ValueError(f"Models use inconsistent outcomes for {outcome_key}")
        observed[outcome_key] = outcome_identity

        error = forecast_value - observed_value
        result.append(
            {
                "model_id": model_id,
                "round_number": round_number,
                "reference_date": reference_date,
                "target_end_date": target_end_date,
                "target": row["target"],
                "horizon": horizon,
                "location": location,
                "location_name": row["location_name"],
                "forecast_kind": "nowcast" if horizon == 0 else "forecast",
                "forecast_value": _format_number(forecast_value),
                "observed_value": _format_number(observed_value),
                "error": _format_number(error),
                "absolute_error": _format_number(abs(error)),
                "squared_error": _format_number(error * error),
                "outcome_data_version": row["outcome_data_version"],
                "forecast_file": row["forecast_file"],
            }
        )
    return sorted(
        result,
        key=lambda row: (
            row["model_id"],
            row["location"],
            row["horizon"],
            row["reference_date"],
        ),
    )


def _summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [float(row["error"]) for row in rows]
    absolute_errors = [float(row["absolute_error"]) for row in rows]
    squared_errors = [float(row["squared_error"]) for row in rows]
    versions = {str(row["outcome_data_version"]) for row in rows}
    if len(versions) != 1:
        raise ValueError("A score group contains more than one outcome data version")
    return {
        "n": len(rows),
        "mae": _format_number(sum(absolute_errors) / len(rows)),
        "bias": _format_number(sum(errors) / len(rows)),
        "rmse": _format_number(math.sqrt(sum(squared_errors) / len(rows))),
        "first_reference_date": min(str(row["reference_date"]) for row in rows),
        "last_reference_date": max(str(row["reference_date"]) for row in rows),
        "outcome_data_version": versions.pop(),
    }


def metrics_by_location_horizon(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["model_id"], row["location"], row["horizon"])].append(row)
    result = []
    for (model_id, location, horizon), group in sorted(grouped.items()):
        result.append(
            {
                "model_id": model_id,
                "location": location,
                "location_name": group[0]["location_name"],
                "horizon": horizon,
                "forecast_kind": "nowcast" if horizon == 0 else "forecast",
                **_summarize_group(group),
            }
        )
    return result


def metrics_by_forecast_kind(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["model_id"], row["location"], row["forecast_kind"])].append(row)
    result = []
    for (model_id, location, forecast_kind), group in sorted(grouped.items()):
        result.append(
            {
                "model_id": model_id,
                "location": location,
                "location_name": group[0]["location_name"],
                "forecast_kind": forecast_kind,
                **_summarize_group(group),
            }
        )
    return result


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    path: Path,
    errors: list[dict[str, Any]],
    horizon_metrics: list[dict[str, Any]],
    kind_metrics: list[dict[str, Any]],
) -> None:
    models = sorted({str(row["model_id"]) for row in errors})
    report = {
        "status": "complete",
        "metrics": ["mae", "bias", "rmse"],
        "bias_definition": "forecast_value - observed_value",
        "ranking_created": False,
        "model_count": len(models),
        "models": models,
        "point_error_row_count": len(errors),
        "location_horizon_group_count": len(horizon_metrics),
        "forecast_kind_group_count": len(kind_metrics),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--input",
        type=Path,
        default=Path("evaluation-output/2025-2026/matched-forecasts.csv"),
    )
    result.add_argument(
        "--output-root",
        type=Path,
        default=Path("evaluation-output/2025-2026"),
    )
    result.add_argument(
        "--allow-empty",
        action="store_true",
        help="Write header-only outputs instead of failing when input has no rows",
    )
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        matched = read_matches(args.input)
        if not matched and not args.allow_empty:
            raise ValueError("Matched forecast data contains no rows")
        errors = point_errors(matched)
        horizon_metrics = metrics_by_location_horizon(errors)
        kind_metrics = metrics_by_forecast_kind(errors)
        write_csv(args.output_root / "point-errors.csv", POINT_ERROR_COLUMNS, errors)
        write_csv(
            args.output_root / "point-metrics-by-location-horizon.csv",
            HORIZON_METRIC_COLUMNS,
            horizon_metrics,
        )
        write_csv(
            args.output_root / "point-metrics-by-forecast-kind.csv",
            KIND_METRIC_COLUMNS,
            kind_metrics,
        )
        write_report(
            args.output_root / "point-score-report.json",
            errors,
            horizon_metrics,
            kind_metrics,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Retrospective point scoring failed: {exc}") from exc
    print(f"Scored {len(errors)} individual point forecasts")
    print(f"Wrote point-score artifacts to {args.output_root}")


if __name__ == "__main__":
    main()
