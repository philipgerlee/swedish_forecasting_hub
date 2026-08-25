"""Generate the permanent retrospective demonstration-model forecasts.

Run from the repository root:

    python demo-models/generate_demo_forecasts.py
    python demo-models/generate_demo_forecasts.py --check

Only the hub's round-specific target data are used. Each location is modelled
independently, and every forecast is based on observations available by the
round's data cutoff.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

LOCATIONS = ("SE", "SE-M", "SE-O")
HORIZONS = (0, 1, 2, 3)
TARGET = "weekly incident influenza cases"
OUTPUT_COLUMNS = (
    "reference_date",
    "target",
    "horizon",
    "location",
    "output_type",
    "output_type_id",
    "value",
)
MANIFEST = Path("retrospective-data/2025-2026/manifest.csv")
ROUND_ROOT = Path("retrospective-data/2025-2026/rounds")
OUTPUT_ROOT = Path("model-output")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _linear_parameters(values: list[float]) -> tuple[float, float]:
    """Return intercept and slope for equally spaced observations."""
    x_mean = (len(values) - 1) / 2
    y_mean = _mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return y_mean, 0.0
    slope = sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(values)
    ) / denominator
    return y_mean - slope * x_mean, slope


def persistence(values: list[float], steps_ahead: int) -> float:
    return values[-1]


def trailing_mean(window: int) -> Callable[[list[float], int], float]:
    def forecast(values: list[float], steps_ahead: int) -> float:
        return _mean(values[-window:])

    return forecast


def linear_trend(values: list[float], steps_ahead: int) -> float:
    recent = values[-4:]
    intercept, slope = _linear_parameters(recent)
    return max(0.0, intercept + slope * (len(recent) - 1 + steps_ahead))


def damped_trend(values: list[float], steps_ahead: int) -> float:
    recent = values[-4:]
    _, slope = _linear_parameters(recent)
    damping = 0.8
    accumulated_change = slope * sum(
        damping**step for step in range(1, steps_ahead + 1)
    )
    return max(0.0, recent[-1] + accumulated_change)


def exponential_trend(values: list[float], steps_ahead: int) -> float:
    recent = [math.log1p(value) for value in values[-4:]]
    intercept, slope = _linear_parameters(recent)
    prediction = math.expm1(intercept + slope * (len(recent) - 1 + steps_ahead))
    return max(0.0, prediction)


MODELS: dict[str, Callable[[list[float], int], float]] = {
    "hubdemo-persistence": persistence,
    "hubdemo-mean3": trailing_mean(3),
    "hubdemo-mean6": trailing_mean(6),
    "hubdemo-linear4": linear_trend,
    "hubdemo-damped4": damped_trend,
    "hubdemo-exptrend4": exponential_trend,
}


def read_series(path: Path, cutoff: date) -> dict[str, list[float]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"location", "target_end_date", "value", "status"}
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"{path} is missing columns: {missing}")
        dated: dict[str, list[tuple[date, float]]] = {
            location: [] for location in LOCATIONS
        }
        for row in reader:
            location = row["location"]
            if location not in dated or row["status"] != "available":
                continue
            target_end_date = date.fromisoformat(row["target_end_date"])
            if target_end_date <= cutoff and row["value"].strip():
                dated[location].append((target_end_date, float(row["value"])))

    result: dict[str, list[float]] = {}
    for location, observations in dated.items():
        observations.sort()
        dates = [observation_date for observation_date, _ in observations]
        if len(dates) != len(set(dates)):
            raise ValueError(f"Duplicate observations for {location} in {path}")
        if len(observations) < 6:
            raise ValueError(f"At least six observations are required for {location}")
        result[location] = [value for _, value in observations]
    return result


def render_forecast(
    model_id: str,
    model: Callable[[list[float], int], float],
    reference_date: date,
    series: dict[str, list[float]],
) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=OUTPUT_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for location in LOCATIONS:
        for horizon in HORIZONS:
            value = model(series[location], horizon + 1)
            if not math.isfinite(value) or value < 0:
                raise ValueError(
                    f"{model_id} produced an invalid value for {location}, "
                    f"horizon {horizon}"
                )
            writer.writerow(
                {
                    "reference_date": reference_date.isoformat(),
                    "target": TARGET,
                    "horizon": horizon,
                    "location": location,
                    "output_type": "mean",
                    "output_type_id": "",
                    "value": f"{value:.6f}",
                }
            )
    return buffer.getvalue()


def expected_files() -> dict[Path, str]:
    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as handle:
        rounds = list(csv.DictReader(handle))
    if len(rounds) != 33:
        raise ValueError("The retrospective manifest must contain 33 rounds")

    result: dict[Path, str] = {}
    for round_row in rounds:
        reference_date = date.fromisoformat(round_row["reference_date"])
        cutoff = date.fromisoformat(round_row["data_cutoff"])
        if cutoff != reference_date - timedelta(days=7):
            raise ValueError(f"Unexpected cutoff for {reference_date}")
        input_path = ROUND_ROOT / f"{reference_date.isoformat()}.csv"
        series = read_series(input_path, cutoff)
        for model_id, model in MODELS.items():
            path = (
                OUTPUT_ROOT
                / model_id
                / f"{reference_date.isoformat()}-{model_id}.csv"
            )
            result[path] = render_forecast(model_id, model, reference_date, series)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that committed forecasts exactly match regenerated output",
    )
    args = parser.parse_args()

    generated = expected_files()
    if args.check:
        mismatches = [
            path
            for path, expected in generated.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != expected
        ]
        if mismatches:
            joined = "\n".join(str(path) for path in mismatches)
            raise SystemExit(f"Demonstration forecasts need regeneration:\n{joined}")
        print(f"Verified {len(generated)} demonstration forecast files")
        return

    for path, contents in generated.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    print(f"Wrote {len(generated)} demonstration forecast files")


if __name__ == "__main__":
    main()
