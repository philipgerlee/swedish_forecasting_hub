"""Score retrospective QRA forecasts with WIS and interval coverage."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .qra import QUANTILES
from .score import read_matches

INTERVALS = (
    (50, 0.5, 0.25, 0.75),
    (80, 0.2, 0.1, 0.9),
    (95, 0.05, 0.025, 0.975),
)
REQUIRED_QRA_COLUMNS = (
    "reference_date",
    "target_end_date",
    "target",
    "horizon",
    "location",
    "location_name",
    "output_type",
    "output_type_id",
    "value",
    "outcome_data_version",
)
QRA_SCORE_COLUMNS = (
    "reference_date",
    "target_end_date",
    "target",
    "horizon",
    "location",
    "location_name",
    "forecast_kind",
    "observed_value",
    "median",
    "wis",
    "covered_50",
    "covered_80",
    "covered_95",
    "outcome_data_version",
)
QRA_METRIC_COLUMNS = (
    "location",
    "location_name",
    "horizon",
    "forecast_kind",
    "n",
    "mean_wis",
    "coverage_50",
    "nominal_coverage_50",
    "coverage_80",
    "nominal_coverage_80",
    "coverage_95",
    "nominal_coverage_95",
    "first_reference_date",
    "last_reference_date",
    "outcome_data_version",
)


def _number(value: str, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} is not numeric: {value!r}") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{context} must be finite and at least zero")
    return result


def _format_number(value: float) -> str:
    return format(value, ".12g")


def read_qra(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(REQUIRED_QRA_COLUMNS) - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"QRA data is missing columns: {missing}")
        return list(reader)


def interval_score(observed: float, lower: float, upper: float, alpha: float) -> float:
    """Return the central (1-alpha) interval score."""
    if not 0 < alpha < 1:
        raise ValueError("alpha must be strictly between zero and one")
    if lower > upper:
        raise ValueError("Interval lower bound exceeds upper bound")
    score = upper - lower
    if observed < lower:
        score += (2 / alpha) * (lower - observed)
    elif observed > upper:
        score += (2 / alpha) * (observed - upper)
    return score


def weighted_interval_score(
    observed: float, quantiles: dict[float, float]
) -> float:
    """Return WIS with median weight 1/2 and interval weight alpha/2."""
    if set(quantiles) != set(QUANTILES):
        missing = sorted(set(QUANTILES) - set(quantiles))
        extra = sorted(set(quantiles) - set(QUANTILES))
        raise ValueError(f"Unexpected quantile set; missing {missing}, extra {extra}")
    numerator = 0.5 * abs(observed - quantiles[0.5])
    for _, alpha, lower_quantile, upper_quantile in INTERVALS:
        numerator += (alpha / 2) * interval_score(
            observed,
            quantiles[lower_quantile],
            quantiles[upper_quantile],
            alpha,
        )
    return numerator / (len(INTERVALS) + 0.5)


def _task_key(row: dict[str, str], context: str) -> tuple[str, str, str, int, str]:
    try:
        horizon = int(row["horizon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid horizon in {context}") from exc
    if horizon not in (0, 1, 2, 3):
        raise ValueError(f"Unsupported horizon in {context}: {horizon}")
    values = (
        row["reference_date"].strip(),
        row["target_end_date"].strip(),
        row["target"].strip(),
        row["location"].strip(),
    )
    if not all(values):
        raise ValueError(f"Task identifiers must not be empty in {context}")
    return values[0], values[1], values[2], horizon, values[3]


def _outcomes(
    matched_rows: Iterable[dict[str, str]],
) -> dict[tuple[str, str, str, int, str], tuple[float, str, str]]:
    result: dict[tuple[str, str, str, int, str], tuple[float, str, str]] = {}
    for row_number, row in enumerate(matched_rows, start=2):
        context = f"matched row {row_number}"
        key = _task_key(row, context)
        identity = (
            _number(row["observed_value"], f"Outcome in {context}"),
            row["location_name"].strip(),
            row["outcome_data_version"].strip(),
        )
        if key in result and result[key] != identity:
            raise ValueError(f"Models use inconsistent outcomes for {key}")
        result[key] = identity
    return result


def score_qra(
    qra_rows: Iterable[dict[str, str]],
    matched_rows: Iterable[dict[str, str]],
) -> list[dict[str, Any]]:
    outcomes = _outcomes(matched_rows)
    tasks: dict[tuple[str, str, str, int, str], dict[str, Any]] = {}
    for row_number, row in enumerate(qra_rows, start=2):
        context = f"QRA row {row_number}"
        key = _task_key(row, context)
        if row["output_type"].strip() != "quantile":
            raise ValueError(f"QRA output_type must be quantile in {context}")
        try:
            quantile = float(row["output_type_id"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid quantile in {context}") from exc
        if quantile not in QUANTILES:
            raise ValueError(f"Unsupported quantile in {context}: {quantile}")
        value = _number(row["value"], f"QRA value in {context}")
        task = tasks.setdefault(
            key,
            {
                "location_name": row["location_name"].strip(),
                "outcome_data_version": row["outcome_data_version"].strip(),
                "quantiles": {},
            },
        )
        identity = (
            task["location_name"],
            task["outcome_data_version"],
        )
        incoming = (
            row["location_name"].strip(),
            row["outcome_data_version"].strip(),
        )
        if identity != incoming:
            raise ValueError(f"QRA rows disagree about task metadata in {context}")
        if quantile in task["quantiles"]:
            raise ValueError(f"Duplicate QRA quantile in {context}: {quantile}")
        task["quantiles"][quantile] = value

    result: list[dict[str, Any]] = []
    for key, task in tasks.items():
        if key not in outcomes:
            raise ValueError(f"No fixed outcome found for QRA task {key}")
        observed, location_name, outcome_version = outcomes[key]
        if (task["location_name"], task["outcome_data_version"]) != (
            location_name,
            outcome_version,
        ):
            raise ValueError(f"QRA and matched outcome metadata disagree for {key}")
        quantiles = task["quantiles"]
        if set(quantiles) != set(QUANTILES):
            missing = sorted(set(QUANTILES) - set(quantiles))
            extra = sorted(set(quantiles) - set(QUANTILES))
            raise ValueError(
                f"Unexpected quantile set for QRA task {key}; "
                f"missing {missing}, extra {extra}"
            )
        values = [quantiles[quantile] for quantile in QUANTILES]
        if values != sorted(values):
            raise ValueError(f"QRA quantiles are not monotone for task {key}")

        reference_date, target_end_date, target, horizon, location = key
        coverage = {
            level: quantiles[lower] <= observed <= quantiles[upper]
            for level, _, lower, upper in INTERVALS
        }
        result.append(
            {
                "reference_date": reference_date,
                "target_end_date": target_end_date,
                "target": target,
                "horizon": horizon,
                "location": location,
                "location_name": location_name,
                "forecast_kind": "nowcast" if horizon == 0 else "forecast",
                "observed_value": _format_number(observed),
                "median": _format_number(quantiles[0.5]),
                "wis": _format_number(weighted_interval_score(observed, quantiles)),
                "covered_50": str(coverage[50]).lower(),
                "covered_80": str(coverage[80]).lower(),
                "covered_95": str(coverage[95]).lower(),
                "outcome_data_version": outcome_version,
            }
        )
    return sorted(
        result,
        key=lambda row: (row["location"], row["horizon"], row["reference_date"]),
    )


def metrics_by_location_horizon(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["location"], row["horizon"])].append(row)
    result = []
    for (location, horizon), group in sorted(grouped.items()):
        versions = {str(row["outcome_data_version"]) for row in group}
        if len(versions) != 1:
            raise ValueError("A QRA score group contains multiple outcome versions")
        result.append(
            {
                "location": location,
                "location_name": group[0]["location_name"],
                "horizon": horizon,
                "forecast_kind": "nowcast" if horizon == 0 else "forecast",
                "n": len(group),
                "mean_wis": _format_number(
                    sum(float(row["wis"]) for row in group) / len(group)
                ),
                "coverage_50": _format_number(
                    sum(row["covered_50"] == "true" for row in group) / len(group)
                ),
                "nominal_coverage_50": "0.5",
                "coverage_80": _format_number(
                    sum(row["covered_80"] == "true" for row in group) / len(group)
                ),
                "nominal_coverage_80": "0.8",
                "coverage_95": _format_number(
                    sum(row["covered_95"] == "true" for row in group) / len(group)
                ),
                "nominal_coverage_95": "0.95",
                "first_reference_date": min(row["reference_date"] for row in group),
                "last_reference_date": max(row["reference_date"] for row in group),
                "outcome_data_version": versions.pop(),
            }
        )
    return result


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


def write_report(
    path: Path,
    scores: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    report = {
        "status": "complete",
        "method": "weighted interval score and empirical interval coverage",
        "method_reference_doi": "10.1371/journal.pcbi.1008618",
        "metrics": ["wis", "coverage_50", "coverage_80", "coverage_95"],
        "wis_definition": (
            "[0.5*absolute_median_error + sum(alpha/2*interval_score_alpha)] "
            "/ (K+0.5), with K=3"
        ),
        "central_intervals": {
            "50": [0.25, 0.75],
            "80": [0.1, 0.9],
            "95": [0.025, 0.975],
        },
        "coverage_boundary_inclusive": True,
        "interval_width_reported_separately": False,
        "ranking_created": False,
        "qra_task_score_count": len(scores),
        "location_horizon_group_count": len(metrics),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--qra-input",
        type=Path,
        default=Path("evaluation-output/2025-2026/qra-forecasts.csv"),
    )
    result.add_argument(
        "--matched-input",
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
        qra_rows = read_qra(args.qra_input)
        if not qra_rows and not args.allow_empty:
            raise ValueError("QRA forecast data contains no rows")
        matched_rows = read_matches(args.matched_input)
        scores = score_qra(qra_rows, matched_rows)
        metrics = metrics_by_location_horizon(scores)
        write_csv(args.output_root / "qra-scores.csv", QRA_SCORE_COLUMNS, scores)
        write_csv(
            args.output_root / "qra-metrics-by-location-horizon.csv",
            QRA_METRIC_COLUMNS,
            metrics,
        )
        write_report(args.output_root / "qra-score-report.json", scores, metrics)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Retrospective QRA scoring failed: {exc}") from exc
    print(f"Scored {len(scores)} probabilistic QRA forecasts")
    print(f"Wrote QRA score artifacts to {args.output_root}")


if __name__ == "__main__":
    main()
