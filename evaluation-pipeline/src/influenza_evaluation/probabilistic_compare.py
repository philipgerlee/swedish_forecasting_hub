"""Compare retrospective QRA and baseline probabilistic forecasts."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .probabilistic_score import (
    QRA_METRIC_COLUMNS,
    QRA_SCORE_COLUMNS,
    _format_number,
    metrics_by_location_horizon,
    read_qra,
    score_qra,
    write_csv,
)
from .score import read_matches

COMPARISON_COLUMNS = (
    "reference_date",
    "target_end_date",
    "target",
    "horizon",
    "location",
    "location_name",
    "forecast_kind",
    "observed_value",
    "qra_wis",
    "baseline_wis",
    "wis_difference",
    "wis_skill",
    "qra_covered_50",
    "baseline_covered_50",
    "qra_covered_80",
    "baseline_covered_80",
    "qra_covered_95",
    "baseline_covered_95",
    "outcome_data_version",
)
COMPARISON_METRIC_COLUMNS = (
    "location",
    "location_name",
    "horizon",
    "forecast_kind",
    "n",
    "mean_qra_wis",
    "mean_baseline_wis",
    "relative_wis",
    "wis_skill",
    "qra_coverage_50",
    "baseline_coverage_50",
    "nominal_coverage_50",
    "qra_coverage_80",
    "baseline_coverage_80",
    "nominal_coverage_80",
    "qra_coverage_95",
    "baseline_coverage_95",
    "nominal_coverage_95",
    "first_reference_date",
    "last_reference_date",
    "outcome_data_version",
)


def _key(row: dict[str, Any]) -> tuple[str, str, str, int, str]:
    return (
        str(row["reference_date"]),
        str(row["target_end_date"]),
        str(row["target"]),
        int(row["horizon"]),
        str(row["location"]),
    )


def compare_scores(
    qra_scores: list[dict[str, Any]],
    baseline_scores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    qra_by_key = {_key(row): row for row in qra_scores}
    baseline_by_key = {_key(row): row for row in baseline_scores}
    if len(qra_by_key) != len(qra_scores) or len(baseline_by_key) != len(baseline_scores):
        raise ValueError("Probabilistic scores contain duplicate tasks")
    missing = sorted(set(qra_by_key) - set(baseline_by_key))
    if missing:
        raise ValueError(f"Baseline is missing {len(missing)} QRA tasks")

    result = []
    for key in sorted(qra_by_key, key=lambda item: (item[4], item[3], item[0])):
        qra = qra_by_key[key]
        baseline = baseline_by_key[key]
        identity_fields = (
            "location_name",
            "forecast_kind",
            "observed_value",
            "outcome_data_version",
        )
        if any(str(qra[field]) != str(baseline[field]) for field in identity_fields):
            raise ValueError(f"QRA and baseline score metadata disagree for {key}")
        qra_wis = float(qra["wis"])
        baseline_wis = float(baseline["wis"])
        result.append(
            {
                "reference_date": key[0],
                "target_end_date": key[1],
                "target": key[2],
                "horizon": key[3],
                "location": key[4],
                "location_name": qra["location_name"],
                "forecast_kind": qra["forecast_kind"],
                "observed_value": qra["observed_value"],
                "qra_wis": qra["wis"],
                "baseline_wis": baseline["wis"],
                "wis_difference": _format_number(qra_wis - baseline_wis),
                "wis_skill": (
                    _format_number(1 - qra_wis / baseline_wis)
                    if baseline_wis > 0
                    else ""
                ),
                "qra_covered_50": qra["covered_50"],
                "baseline_covered_50": baseline["covered_50"],
                "qra_covered_80": qra["covered_80"],
                "baseline_covered_80": baseline["covered_80"],
                "qra_covered_95": qra["covered_95"],
                "baseline_covered_95": baseline["covered_95"],
                "outcome_data_version": qra["outcome_data_version"],
            }
        )
    return result


def comparison_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["location"]), int(row["horizon"]))].append(row)
    result = []
    for (location, horizon), group in sorted(grouped.items()):
        versions = {str(row["outcome_data_version"]) for row in group}
        if len(versions) != 1:
            raise ValueError("A comparison group contains multiple outcome versions")
        mean_qra = sum(float(row["qra_wis"]) for row in group) / len(group)
        mean_baseline = sum(float(row["baseline_wis"]) for row in group) / len(group)
        result.append(
            {
                "location": location,
                "location_name": group[0]["location_name"],
                "horizon": horizon,
                "forecast_kind": "nowcast" if horizon == 0 else "forecast",
                "n": len(group),
                "mean_qra_wis": _format_number(mean_qra),
                "mean_baseline_wis": _format_number(mean_baseline),
                "relative_wis": (
                    _format_number(mean_qra / mean_baseline) if mean_baseline > 0 else ""
                ),
                "wis_skill": (
                    _format_number(1 - mean_qra / mean_baseline)
                    if mean_baseline > 0
                    else ""
                ),
                "qra_coverage_50": _coverage(group, "qra_covered_50"),
                "baseline_coverage_50": _coverage(group, "baseline_covered_50"),
                "nominal_coverage_50": "0.5",
                "qra_coverage_80": _coverage(group, "qra_covered_80"),
                "baseline_coverage_80": _coverage(group, "baseline_covered_80"),
                "nominal_coverage_80": "0.8",
                "qra_coverage_95": _coverage(group, "qra_covered_95"),
                "baseline_coverage_95": _coverage(group, "baseline_covered_95"),
                "nominal_coverage_95": "0.95",
                "first_reference_date": min(str(row["reference_date"]) for row in group),
                "last_reference_date": max(str(row["reference_date"]) for row in group),
                "outcome_data_version": versions.pop(),
            }
        )
    return result


def _coverage(rows: list[dict[str, Any]], field: str) -> str:
    return _format_number(sum(row[field] == "true" for row in rows) / len(rows))


def write_report(
    path: Path,
    qra_scores: list[dict[str, Any]],
    baseline_scores: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    report = {
        "status": "complete",
        "comparison": "regularized QRA versus hub-normalma3",
        "task_rule": "only tasks for which both QRA and baseline forecasts exist",
        "wis_skill_definition": "1 - mean_qra_wis / mean_baseline_wis",
        "positive_wis_skill_means": "QRA has lower mean WIS than the baseline",
        "qra_score_count": len(qra_scores),
        "baseline_score_count": len(baseline_scores),
        "common_task_count": len(comparisons),
        "location_horizon_group_count": len(metrics),
        "coverage_levels": [0.5, 0.8, 0.95],
        "interval_width_reported_separately": False,
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
        "--baseline-input",
        type=Path,
        default=Path("evaluation-output/2025-2026/normal-ma3-baseline-forecasts.csv"),
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
        baseline_rows = read_qra(args.baseline_input)
        if (not qra_rows or not baseline_rows) and not args.allow_empty:
            raise ValueError("Probabilistic comparison input contains no rows")
        matched_rows = read_matches(args.matched_input)
        qra_scores = score_qra(qra_rows, matched_rows)
        baseline_scores = score_qra(baseline_rows, matched_rows)
        baseline_metrics = metrics_by_location_horizon(baseline_scores)
        comparisons = compare_scores(qra_scores, baseline_scores)
        metrics = comparison_metrics(comparisons)
        write_csv(
            args.output_root / "normal-ma3-baseline-scores.csv",
            QRA_SCORE_COLUMNS,
            baseline_scores,
        )
        write_csv(
            args.output_root / "normal-ma3-baseline-metrics-by-location-horizon.csv",
            QRA_METRIC_COLUMNS,
            baseline_metrics,
        )
        write_csv(
            args.output_root / "probabilistic-comparison.csv",
            COMPARISON_COLUMNS,
            comparisons,
        )
        write_csv(
            args.output_root / "probabilistic-comparison-by-location-horizon.csv",
            COMPARISON_METRIC_COLUMNS,
            metrics,
        )
        write_report(
            args.output_root / "probabilistic-comparison-report.json",
            qra_scores,
            baseline_scores,
            comparisons,
            metrics,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Probabilistic comparison failed: {exc}") from exc
    print(f"Compared QRA and baseline on {len(comparisons)} common tasks")
    print(f"Wrote probabilistic comparison artifacts to {args.output_root}")


if __name__ == "__main__":
    main()
