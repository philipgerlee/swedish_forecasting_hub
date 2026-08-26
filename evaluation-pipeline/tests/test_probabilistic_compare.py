from __future__ import annotations

import unittest

from influenza_evaluation.probabilistic_compare import (
    compare_scores,
    comparison_metrics,
)


def score(*, model_wis: float, reference_date: str = "2025-11-30") -> dict[str, object]:
    return {
        "reference_date": reference_date,
        "target_end_date": reference_date,
        "target": "weekly incident influenza cases",
        "horizon": 0,
        "location": "SE",
        "location_name": "Sverige",
        "forecast_kind": "nowcast",
        "observed_value": "5",
        "median": "5",
        "wis": str(model_wis),
        "covered_50": "true",
        "covered_80": "true",
        "covered_95": "true",
        "outcome_data_version": "fixed-version",
    }


class ProbabilisticComparisonTests(unittest.TestCase):
    def test_compares_only_matched_tasks_and_calculates_skill(self):
        qra = [score(model_wis=8)]
        baseline = [score(model_wis=10), score(model_wis=5, reference_date="2025-12-07")]
        compared = compare_scores(qra, baseline)
        self.assertEqual(len(compared), 1)
        self.assertEqual(compared[0]["wis_difference"], "-2")
        self.assertEqual(compared[0]["wis_skill"], "0.2")

    def test_group_skill_is_ratio_of_mean_wis(self):
        qra = [score(model_wis=8), score(model_wis=4, reference_date="2025-12-07")]
        baseline = [score(model_wis=10), score(model_wis=10, reference_date="2025-12-07")]
        metrics = comparison_metrics(compare_scores(qra, baseline))[0]
        self.assertEqual(metrics["n"], 2)
        self.assertEqual(metrics["mean_qra_wis"], "6")
        self.assertEqual(metrics["mean_baseline_wis"], "10")
        self.assertEqual(metrics["relative_wis"], "0.6")
        self.assertEqual(metrics["wis_skill"], "0.4")

    def test_rejects_missing_baseline_tasks(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            compare_scores([score(model_wis=8)], [])


if __name__ == "__main__":
    unittest.main()
