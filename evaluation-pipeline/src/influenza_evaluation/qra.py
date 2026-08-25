"""Build temporally ordered LASSO Quantile Regression Averaging forecasts."""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sklearn.linear_model import QuantileRegressor

from .score import read_matches

QUANTILES = (0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975)
ALPHAS = (0.0, 0.001, 0.01, 0.1, 1.0)
MIN_TRAINING_SAMPLES = 8
MIN_CV_TRAINING_SAMPLES = 4

QRA_COLUMNS = (
    "reference_date",
    "target_end_date",
    "target",
    "horizon",
    "location",
    "location_name",
    "output_type",
    "output_type_id",
    "value",
    "raw_value",
    "training_sample_count",
    "training_last_target_end_date",
    "component_model_count",
    "component_models",
    "selected_alpha",
    "quantile_crossing_adjusted",
    "outcome_data_version",
)
COEFFICIENT_COLUMNS = (
    "reference_date",
    "horizon",
    "location",
    "output_type_id",
    "term",
    "coefficient",
    "selected_alpha",
    "training_sample_count",
)


@dataclass(frozen=True)
class PanelCell:
    reference_date: date
    target_end_date: date
    target: str
    horizon: int
    location: str
    location_name: str
    observed_value: float
    outcome_data_version: str
    forecasts: dict[str, float]


@dataclass(frozen=True)
class FittedQuantile:
    prediction: float
    intercept: float
    coefficients: tuple[float, ...]
    alpha: float


def _number(value: str, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} is not numeric: {value!r}") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{context} must be finite and at least zero")
    return result


def build_panel(rows: Iterable[dict[str, str]]) -> tuple[list[PanelCell], tuple[str, ...]]:
    cells: dict[tuple[date, str, int], dict[str, Any]] = {}
    all_models: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        context = f"matched row {row_number}"
        try:
            reference_date = date.fromisoformat(row["reference_date"])
            target_end_date = date.fromisoformat(row["target_end_date"])
            horizon = int(row["horizon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid date or horizon in {context}") from exc
        model_id = row["model_id"].strip()
        location = row["location"].strip()
        key = (reference_date, location, horizon)
        forecast = _number(row["forecast_value"], f"Forecast in {context}")
        observed = _number(row["observed_value"], f"Outcome in {context}")
        cell = cells.setdefault(
            key,
            {
                "reference_date": reference_date,
                "target_end_date": target_end_date,
                "target": row["target"],
                "horizon": horizon,
                "location": location,
                "location_name": row["location_name"],
                "observed_value": observed,
                "outcome_data_version": row["outcome_data_version"],
                "forecasts": {},
            },
        )
        identity = (
            cell["target_end_date"],
            cell["target"],
            cell["location_name"],
            cell["observed_value"],
            cell["outcome_data_version"],
        )
        incoming = (
            target_end_date,
            row["target"],
            row["location_name"],
            observed,
            row["outcome_data_version"],
        )
        if identity != incoming:
            raise ValueError(f"Models disagree about task or outcome in {context}")
        if model_id in cell["forecasts"]:
            raise ValueError(f"Duplicate model forecast in {context}: {model_id}")
        cell["forecasts"][model_id] = forecast
        all_models.add(model_id)

    models = tuple(sorted(all_models))
    result = []
    for cell in cells.values():
        if set(cell["forecasts"]) != set(models):
            missing = sorted(set(models) - set(cell["forecasts"]))
            raise ValueError(
                f"Component set is incomplete for {cell['reference_date']}, "
                f"{cell['location']}, horizon {cell['horizon']}: {missing}"
            )
        result.append(PanelCell(**cell))
    return sorted(
        result,
        key=lambda cell: (cell.location, cell.horizon, cell.reference_date),
    ), models


def _scaled_fit(
    x: np.ndarray,
    y: np.ndarray,
    x_new: np.ndarray,
    *,
    quantile: float,
    alpha: float,
) -> FittedQuantile:
    x_mean = x.mean(axis=0)
    x_scale = x.std(axis=0)
    x_scale[x_scale == 0] = 1.0
    y_mean = float(y.mean())
    y_scale = float(y.std())
    if y_scale == 0:
        y_scale = 1.0
    x_scaled = (x - x_mean) / x_scale
    y_scaled = (y - y_mean) / y_scale
    model = QuantileRegressor(
        quantile=quantile,
        alpha=alpha,
        fit_intercept=True,
        solver="highs",
    )
    model.fit(x_scaled, y_scaled)
    scaled_coefficients = np.asarray(model.coef_, dtype=float)
    coefficients = y_scale * scaled_coefficients / x_scale
    intercept = (
        y_mean
        + y_scale * float(model.intercept_)
        - float(np.dot(coefficients, x_mean))
    )
    prediction = intercept + float(np.dot(coefficients, x_new))
    return FittedQuantile(
        prediction=prediction,
        intercept=intercept,
        coefficients=tuple(float(value) for value in coefficients),
        alpha=alpha,
    )


def _pinball_loss(observed: float, predicted: float, quantile: float) -> float:
    error = observed - predicted
    return quantile * error if error >= 0 else (quantile - 1) * error


def _cv_losses(
    x: np.ndarray,
    y: np.ndarray,
    *,
    quantile: float,
    alphas: tuple[float, ...],
) -> dict[float, list[float]]:
    losses = {alpha: [] for alpha in alphas}
    for validation_index in range(MIN_CV_TRAINING_SAMPLES, len(y)):
        for alpha in alphas:
            fitted = _scaled_fit(
                x[:validation_index],
                y[:validation_index],
                x[validation_index],
                quantile=quantile,
                alpha=alpha,
            )
            losses[alpha].append(
                _pinball_loss(
                    float(y[validation_index]), fitted.prediction, quantile
                )
            )
    return losses


def _select_alpha(
    losses: dict[float, list[float]],
    *,
    training_sample_count: int,
) -> float:
    validation_count = training_sample_count - MIN_CV_TRAINING_SAMPLES
    if validation_count <= 0:
        return max(losses)
    candidates = []
    for alpha, values in losses.items():
        selected = values[:validation_count]
        candidates.append((sum(selected) / len(selected), -alpha, alpha))
    return min(candidates)[2]


def generate_qra(
    cells: list[PanelCell],
    models: tuple[str, ...],
    *,
    quantiles: tuple[float, ...] = QUANTILES,
    alphas: tuple[float, ...] = ALPHAS,
    minimum_training_samples: int = MIN_TRAINING_SAMPLES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if minimum_training_samples < MIN_CV_TRAINING_SAMPLES + 1:
        raise ValueError("minimum_training_samples is too small for forward validation")
    grouped: dict[tuple[str, int], list[PanelCell]] = defaultdict(list)
    for cell in cells:
        grouped[(cell.location, cell.horizon)].append(cell)

    forecasts: list[dict[str, Any]] = []
    coefficients: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for (location, horizon), group in sorted(grouped.items()):
        group.sort(key=lambda cell: cell.reference_date)
        x = np.asarray(
            [[cell.forecasts[model] for model in models] for cell in group],
            dtype=float,
        )
        y = np.asarray([cell.observed_value for cell in group], dtype=float)
        target_dates = [cell.target_end_date for cell in group]
        losses = {
            quantile: _cv_losses(x, y, quantile=quantile, alphas=alphas)
            for quantile in quantiles
        }

        for index, current in enumerate(group):
            information_cutoff = current.reference_date - timedelta(days=7)
            training_count = bisect.bisect_right(target_dates, information_cutoff)
            if training_count < minimum_training_samples:
                skipped.append(
                    {
                        "reference_date": current.reference_date.isoformat(),
                        "location": location,
                        "horizon": horizon,
                        "available_training_samples": training_count,
                        "required_training_samples": minimum_training_samples,
                        "reason": "insufficient_previous_complete_outcomes",
                    }
                )
                continue
            raw_fits = []
            for quantile in quantiles:
                alpha = _select_alpha(
                    losses[quantile], training_sample_count=training_count
                )
                raw_fits.append(
                    _scaled_fit(
                        x[:training_count],
                        y[:training_count],
                        x[index],
                        quantile=quantile,
                        alpha=alpha,
                    )
                )
            nonnegative = [max(0.0, fit.prediction) for fit in raw_fits]
            ordered = sorted(nonnegative)
            crossing_adjusted = any(
                not math.isclose(raw, adjusted, rel_tol=1e-12, abs_tol=1e-12)
                for raw, adjusted in zip(nonnegative, ordered)
            )
            last_training_date = target_dates[training_count - 1].isoformat()
            for quantile, fitted, value in zip(quantiles, raw_fits, ordered):
                forecasts.append(
                    {
                        "reference_date": current.reference_date.isoformat(),
                        "target_end_date": current.target_end_date.isoformat(),
                        "target": current.target,
                        "horizon": horizon,
                        "location": location,
                        "location_name": current.location_name,
                        "output_type": "quantile",
                        "output_type_id": format(quantile, "g"),
                        "value": format(value, ".12g"),
                        "raw_value": format(fitted.prediction, ".12g"),
                        "training_sample_count": training_count,
                        "training_last_target_end_date": last_training_date,
                        "component_model_count": len(models),
                        "component_models": "|".join(models),
                        "selected_alpha": format(fitted.alpha, "g"),
                        "quantile_crossing_adjusted": str(crossing_adjusted).lower(),
                        "outcome_data_version": current.outcome_data_version,
                    }
                )
                terms = [("intercept", fitted.intercept), *zip(models, fitted.coefficients)]
                for term, coefficient in terms:
                    coefficients.append(
                        {
                            "reference_date": current.reference_date.isoformat(),
                            "horizon": horizon,
                            "location": location,
                            "output_type_id": format(quantile, "g"),
                            "term": term,
                            "coefficient": format(coefficient, ".12g"),
                            "selected_alpha": format(fitted.alpha, "g"),
                            "training_sample_count": training_count,
                        }
                    )
    return forecasts, coefficients, skipped


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    path: Path,
    forecasts: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    models: tuple[str, ...],
) -> None:
    starts = {}
    for row in forecasts:
        key = f"{row['location']}|horizon-{row['horizon']}"
        starts.setdefault(key, row["reference_date"])
    report = {
        "status": "complete",
        "method": "LASSO Quantile Regression Averaging (LQRA)",
        "method_reference_doi": "10.1016/j.eneco.2021.105121",
        "penalty": "L1 on standardized model coefficients; intercept unpenalized",
        "standardization": "predictors and outcome standardized within each fit",
        "temporal_training_rule": (
            "target_end_date <= current reference_date - 7 days"
        ),
        "minimum_training_samples": MIN_TRAINING_SAMPLES,
        "quantiles": list(QUANTILES),
        "alpha_grid": list(ALPHAS),
        "alpha_selection": "expanding-window one-step-ahead pinball loss",
        "component_models": list(models),
        "qra_forecast_row_count": len(forecasts),
        "skipped_task_count": len(skipped),
        "first_qra_reference_date_by_task": starts,
        "negative_values_truncated_at_zero": True,
        "quantile_crossings_rearranged": True,
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
    result.add_argument("--allow-empty", action="store_true")
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        matched = read_matches(args.input)
        if not matched and not args.allow_empty:
            raise ValueError("Matched forecast data contains no rows")
        cells, models = build_panel(matched)
        forecasts, coefficients, skipped = generate_qra(cells, models)
        write_csv(args.output_root / "qra-forecasts.csv", QRA_COLUMNS, forecasts)
        write_csv(
            args.output_root / "qra-coefficients.csv",
            COEFFICIENT_COLUMNS,
            coefficients,
        )
        write_report(
            args.output_root / "qra-report.json", forecasts, skipped, models
        )
        skipped_path = args.output_root / "qra-skipped-tasks.json"
        skipped_path.write_text(json.dumps(skipped, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Retrospective QRA build failed: {exc}") from exc
    print(f"Wrote {len(forecasts)} retrospective QRA quantile rows")
    print(f"Skipped {len(skipped)} tasks before sufficient training data")
    print(f"Wrote QRA artifacts to {args.output_root}")


if __name__ == "__main__":
    main()
