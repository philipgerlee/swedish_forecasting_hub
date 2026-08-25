from __future__ import annotations

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

from influenza_evaluation.score import (
    HORIZON_METRIC_COLUMNS,
    KIND_METRIC_COLUMNS,
    POINT_ERROR_COLUMNS,
    metrics_by_forecast_kind,
    metrics_by_location_horizon,
    point_errors,
    write_csv,
    write_report,
)


def matched_row(
    reference_date: str,
    *,
    horizon: int,
    forecast: float,
    observed: float,
) -> dict[str, str]:
    return {
        "model_id": "example-example",
        "round_number": "1",
        "reference_date": reference_date,
        "target_end_date": reference_date,
        "target": "weekly incident influenza cases",
        "horizon": str(horizon),
        "location": "SE",
        "location_name": "Sverige",
        "output_type": "mean",
        "forecast_value": str(forecast),
        "observed_value": str(observed),
        "outcome_data_version": "fixed-version",
        "forecast_file": "example-example/file.csv",
    }


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.matched = [
            matched_row("2025-10-05", horizon=0, forecast=9, observed=10),
            matched_row("2025-10-12", horizon=0, forecast=11, observed=10),
            matched_row("2025-10-05", horizon=1, forecast=10, observed=10),
            matched_row("2025-10-12", horizon=1, forecast=12, observed=10),
        ]

    def test_calculates_signed_and_unsigned_point_errors(self):
        errors = point_errors(self.matched)
        first = next(
            row
            for row in errors
            if row["reference_date"] == "2025-10-05" and row["horizon"] == 0
        )
        self.assertEqual(first["error"], "-1")
        self.assertEqual(first["absolute_error"], "1")
        self.assertEqual(first["squared_error"], "1")

    def test_calculates_mae_bias_and_rmse_by_horizon(self):
        metrics = metrics_by_location_horizon(point_errors(self.matched))
        nowcast = next(row for row in metrics if row["horizon"] == 0)
        forecast = next(row for row in metrics if row["horizon"] == 1)
        self.assertEqual(nowcast["n"], 2)
        self.assertEqual(nowcast["mae"], "1")
        self.assertEqual(nowcast["bias"], "0")
        self.assertEqual(nowcast["rmse"], "1")
        self.assertEqual(forecast["mae"], "1")
        self.assertEqual(forecast["bias"], "1")
        self.assertAlmostEqual(float(forecast["rmse"]), math.sqrt(2))

    def test_separates_nowcasts_from_true_forecasts(self):
        metrics = metrics_by_forecast_kind(point_errors(self.matched))
        self.assertEqual({row["forecast_kind"] for row in metrics}, {"nowcast", "forecast"})
        self.assertEqual(sum(row["n"] for row in metrics), 4)

    def test_rejects_duplicate_or_inconsistent_rows(self):
        duplicate = [self.matched[0], dict(self.matched[0])]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            point_errors(duplicate)

        inconsistent = [self.matched[0], dict(self.matched[0])]
        inconsistent[1]["model_id"] = "other-model"
        inconsistent[1]["observed_value"] = "99"
        with self.assertRaisesRegex(ValueError, "inconsistent outcomes"):
            point_errors(inconsistent)

    def test_writes_machine_readable_score_artifacts(self):
        errors = point_errors(self.matched)
        horizon_metrics = metrics_by_location_horizon(errors)
        kind_metrics = metrics_by_forecast_kind(errors)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_csv(root / "errors.csv", POINT_ERROR_COLUMNS, errors)
            write_csv(root / "horizon.csv", HORIZON_METRIC_COLUMNS, horizon_metrics)
            write_csv(root / "kind.csv", KIND_METRIC_COLUMNS, kind_metrics)
            write_report(root / "report.json", errors, horizon_metrics, kind_metrics)
            with (root / "errors.csv").open(encoding="utf-8", newline="") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 4)
            report = json.loads((root / "report.json").read_text())
            self.assertEqual(report["metrics"], ["mae", "bias", "rmse"])
            self.assertFalse(report["ranking_created"])


if __name__ == "__main__":
    unittest.main()
