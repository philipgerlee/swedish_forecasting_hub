from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from influenza_evaluation.probabilistic_score import (
    QRA_METRIC_COLUMNS,
    QRA_SCORE_COLUMNS,
    interval_score,
    metrics_by_location_horizon,
    score_qra,
    weighted_interval_score,
    write_csv,
    write_report,
)


QUANTILE_VALUES = {
    0.025: 0.0,
    0.1: 2.0,
    0.25: 4.0,
    0.5: 5.0,
    0.75: 6.0,
    0.9: 8.0,
    0.975: 10.0,
}


def matched_row(observed: float = 5.0) -> dict[str, str]:
    return {
        "model_id": "example-example",
        "round_number": "1",
        "reference_date": "2025-11-30",
        "target_end_date": "2025-11-30",
        "target": "weekly incident influenza cases",
        "horizon": "0",
        "location": "SE",
        "location_name": "Sverige",
        "output_type": "mean",
        "forecast_value": "5",
        "observed_value": str(observed),
        "outcome_data_version": "fixed-version",
        "forecast_file": "example-example/file.csv",
    }


def qra_rows(values: dict[float, float] = QUANTILE_VALUES) -> list[dict[str, str]]:
    return [
        {
            "reference_date": "2025-11-30",
            "target_end_date": "2025-11-30",
            "target": "weekly incident influenza cases",
            "horizon": "0",
            "location": "SE",
            "location_name": "Sverige",
            "output_type": "quantile",
            "output_type_id": str(quantile),
            "value": str(value),
            "outcome_data_version": "fixed-version",
        }
        for quantile, value in values.items()
    ]


class ProbabilisticScoreTests(unittest.TestCase):
    def test_interval_score_penalizes_misses(self):
        self.assertEqual(interval_score(5, 4, 6, 0.5), 2)
        self.assertEqual(interval_score(12, 4, 6, 0.5), 26)

    def test_wis_uses_three_intervals_and_the_median(self):
        self.assertAlmostEqual(weighted_interval_score(5, QUANTILE_VALUES), 1.35 / 3.5)
        self.assertAlmostEqual(weighted_interval_score(12, QUANTILE_VALUES), 16.85 / 3.5)

    def test_scores_wis_and_inclusive_coverage(self):
        score = score_qra(qra_rows(), [matched_row()])[0]
        self.assertAlmostEqual(float(score["wis"]), 1.35 / 3.5)
        self.assertEqual(score["covered_50"], "true")
        self.assertEqual(score["covered_80"], "true")
        self.assertEqual(score["covered_95"], "true")

        boundary = score_qra(qra_rows(), [matched_row(observed=10)])[0]
        self.assertEqual(boundary["covered_95"], "true")
        self.assertEqual(boundary["covered_80"], "false")

    def test_rejects_missing_or_crossing_quantiles(self):
        missing = qra_rows()
        missing.pop()
        with self.assertRaisesRegex(ValueError, "Unexpected quantile set"):
            score_qra(missing, [matched_row()])

        crossing_values = dict(QUANTILE_VALUES)
        crossing_values[0.75] = 3
        with self.assertRaisesRegex(ValueError, "not monotone"):
            score_qra(qra_rows(crossing_values), [matched_row()])

    def test_summarizes_wis_and_coverage_by_location_horizon(self):
        first = score_qra(qra_rows(), [matched_row()])[0]
        second = dict(first)
        second["reference_date"] = "2025-12-07"
        second["wis"] = "1"
        second["covered_50"] = "false"
        metrics = metrics_by_location_horizon([first, second])[0]
        self.assertEqual(metrics["n"], 2)
        self.assertAlmostEqual(float(metrics["mean_wis"]), (1.35 / 3.5 + 1) / 2)
        self.assertEqual(metrics["coverage_50"], "0.5")
        self.assertEqual(metrics["coverage_80"], "1")
        self.assertEqual(metrics["nominal_coverage_95"], "0.95")

    def test_writes_machine_readable_artifacts_without_width_metric(self):
        scores = score_qra(qra_rows(), [matched_row()])
        metrics = metrics_by_location_horizon(scores)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_csv(root / "scores.csv", QRA_SCORE_COLUMNS, scores)
            write_csv(root / "metrics.csv", QRA_METRIC_COLUMNS, metrics)
            write_report(root / "report.json", scores, metrics)
            with (root / "scores.csv").open(encoding="utf-8", newline="") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)
            report = json.loads((root / "report.json").read_text())
            self.assertEqual(report["metrics"], ["wis", "coverage_50", "coverage_80", "coverage_95"])
            self.assertFalse(report["interval_width_reported_separately"])
            self.assertFalse(report["ranking_created"])


if __name__ == "__main__":
    unittest.main()
