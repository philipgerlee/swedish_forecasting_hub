"""Build a Hubverse PredTimeChart view without changing participant submissions."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from .baseline import HUBVERSE_COLUMNS
from .probabilistic_score import read_qra

QRA_MODEL_ID = "hub-qra"
BASELINE_MODEL_ID = "hub-normalma3"
TARGET = "weekly incident influenza cases"
LOCATIONS = {
    "SE": "Sverige",
    "SE-M": "Region Skåne",
    "SE-O": "Västra Götalandsregionen",
}
TARGET_SLUG = "weekly-incident-influenza-cases"
REQUIRED_OUTCOME_COLUMNS = (
    "location",
    "target_end_date",
    "value",
)


def _read_outcomes(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(REQUIRED_OUTCOME_COLUMNS) - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"Final outcomes are missing columns: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError("Final outcomes contain no rows")
    return rows


def _write_csv(
    path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]
) -> None:
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


def _write_model_output(
    root: Path,
    model_id: str,
    rows: list[dict[str, str]],
) -> list[Path]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["reference_date"]].append(
            {column: row[column] for column in HUBVERSE_COLUMNS}
        )
    paths = []
    for reference_date, group in sorted(grouped.items()):
        path = root / model_id / f"{reference_date}-{model_id}.csv"
        _write_csv(path, HUBVERSE_COLUMNS, group)
        paths.append(path)
    return paths


def _tasks(qra_rows: list[dict[str, str]], baseline_rows: list[dict[str, str]]) -> dict[str, Any]:
    forecast_rows = qra_rows + baseline_rows
    reference_dates = sorted({row["reference_date"] for row in forecast_rows})
    target_dates = sorted({row["target_end_date"] for row in forecast_rows})
    return {
        "schema_version": "https://raw.githubusercontent.com/hubverse-org/schemas/main/v6.0.0/tasks-schema.json",
        "output_type_id_datatype": "double",
        "rounds": [
            {
                "round_id_from_variable": True,
                "round_id": "reference_date",
                "model_tasks": [
                    {
                        "task_ids": {
                            "reference_date": {
                                "required": None,
                                "optional": reference_dates,
                            },
                            "target_end_date": {
                                "required": None,
                                "optional": target_dates,
                            },
                            "target": {"required": [TARGET], "optional": None},
                            "horizon": {"required": [0, 1, 2, 3], "optional": None},
                            "location": {
                                "required": None,
                                "optional": list(LOCATIONS),
                            },
                        },
                        "output_type": {
                            "quantile": {
                                "is_required": True,
                                "output_type_id": {
                                    "required": [
                                        0.025,
                                        0.1,
                                        0.25,
                                        0.5,
                                        0.75,
                                        0.9,
                                        0.975,
                                    ]
                                },
                                "value": {"type": "double", "minimum": 0},
                            }
                        },
                        "target_metadata": [
                            {
                                "target_id": "weekly_influenza_cases",
                                "target_name": "Weekly reported influenza cases",
                                "target_units": "count",
                                "target_keys": {"target": TARGET},
                                "description": (
                                    "Laboratory-confirmed influenza cases reported "
                                    "in Folkhälsodata for an ISO week."
                                ),
                                "target_type": "discrete",
                                "is_step_ahead": True,
                                "time_unit": "week",
                            }
                        ],
                    }
                ],
                "submissions_due": {
                    "relative_to": "reference_date",
                    "start": -3,
                    "end": 0,
                },
            }
        ],
    }


def _predtimechart_config() -> str:
    return """---
rounds_idx: 0
reference_date_col_name: reference_date
target_date_col_name: target_end_date
horizon_col_name: horizon
initial_checked_models: [hub-qra, hub-normalma3]
target_data_file_name: time-series.csv
disclaimer: "Demonstration med retrospektiva prognoser för säsongen 2025/26 – inte realtidsprognoser."
task_id_text:
  location:
    SE: Sverige
    SE-M: Region Skåne
    SE-O: Västra Götalandsregionen
"""


def _write_predtimechart_targets(
    root: Path,
    outcomes: list[dict[str, str]],
    reference_dates: list[str],
) -> list[Path]:
    by_location: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in outcomes:
        if row["value"].strip():
            by_location[row["location"]].append(row)
    paths = []
    for location in LOCATIONS:
        location_rows = sorted(
            by_location[location], key=lambda row: row["target_end_date"]
        )
        payload = {
            "date": [row["target_end_date"] for row in location_rows],
            "y": [float(row["value"]) for row in location_rows],
        }
        for reference_date in reference_dates:
            path = root / f"{TARGET_SLUG}_{location}_{reference_date}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
            paths.append(path)
    return paths


def build_dashboard_view(
    *,
    output_root: Path,
    qra_input: Path,
    baseline_input: Path,
    outcomes_input: Path,
    hub_config_root: Path,
    metadata_root: Path,
) -> dict[str, Any]:
    qra_rows = read_qra(qra_input)
    baseline_rows = read_qra(baseline_input)
    if not qra_rows or not baseline_rows:
        raise ValueError("Both QRA and baseline forecasts are required")
    outcomes = _read_outcomes(outcomes_input)

    config_root = output_root / "hub-config"
    config_root.mkdir(parents=True, exist_ok=True)
    for name in ("admin.json", "model-metadata-schema.json"):
        shutil.copyfile(hub_config_root / name, config_root / name)
    (config_root / "tasks.json").write_text(
        json.dumps(_tasks(qra_rows, baseline_rows), indent=2) + "\n",
        encoding="utf-8",
    )

    output_metadata = output_root / "model-metadata"
    output_metadata.mkdir(parents=True, exist_ok=True)
    for model_id in (QRA_MODEL_ID, BASELINE_MODEL_ID):
        shutil.copyfile(
            metadata_root / f"{model_id}.yml",
            output_metadata / f"{model_id}.yml",
        )

    model_output_root = output_root / "model-output"
    qra_paths = _write_model_output(model_output_root, QRA_MODEL_ID, qra_rows)
    baseline_paths = _write_model_output(
        model_output_root, BASELINE_MODEL_ID, baseline_rows
    )

    target_rows = [
        {
            "location": row["location"],
            "date": row["target_end_date"],
            "value": row["value"],
        }
        for row in outcomes
        if row["value"].strip()
    ]
    _write_csv(
        output_root / "target-data" / "time-series.csv",
        ("location", "date", "value"),
        target_rows,
    )
    (output_root / "predtimechart-config.yml").write_text(
        _predtimechart_config(), encoding="utf-8"
    )
    reference_dates = sorted(
        {row["reference_date"] for row in qra_rows + baseline_rows}
    )
    target_json_paths = _write_predtimechart_targets(
        output_root / "predtimechart-targets",
        outcomes,
        reference_dates,
    )

    report = {
        "status": "complete",
        "mode": "demo",
        "season": "2025/26",
        "models": [QRA_MODEL_ID, BASELINE_MODEL_ID],
        "qra_reference_date_count": len(qra_paths),
        "baseline_reference_date_count": len(baseline_paths),
        "location_count": len(LOCATIONS),
        "target_observation_count": len(target_rows),
        "predtimechart_target_file_count": len(target_json_paths),
        "participant_submission_format_changed": False,
    }
    (output_root / "dashboard-view-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output-root", type=Path, required=True)
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
        "--outcomes-input",
        type=Path,
        default=Path("retrospective-data/2025-2026/final-outcomes.csv"),
    )
    result.add_argument("--hub-config-root", type=Path, default=Path("hub-config"))
    result.add_argument("--metadata-root", type=Path, default=Path("model-metadata"))
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        report = build_dashboard_view(
            output_root=args.output_root,
            qra_input=args.qra_input,
            baseline_input=args.baseline_input,
            outcomes_input=args.outcomes_input,
            hub_config_root=args.hub_config_root,
            metadata_root=args.metadata_root,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Dashboard view build failed: {exc}") from exc
    print(
        "Built dashboard view with "
        f"{report['qra_reference_date_count']} QRA rounds and "
        f"{report['baseline_reference_date_count']} baseline rounds"
    )


if __name__ == "__main__":
    main()
