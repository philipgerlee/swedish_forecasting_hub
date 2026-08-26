from __future__ import annotations

import csv
import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from influenza_evaluation.baseline import (
    HUBVERSE_COLUMNS,
    MODEL_ID,
    generate_round,
    write_hubverse_files,
)
from influenza_evaluation.qra import QUANTILES


def round_rows(*, changed_final_value: float | None = None) -> list[dict[str, str]]:
    rows = []
    start = date.fromisoformat("2025-01-05")
    for index in range(41):
        value = float(index + 1)
        if changed_final_value is not None and index == 40:
            value = changed_final_value
        rows.append(
            {
                "location": "SE",
                "location_name": "Sverige",
                "target_end_date": (start + timedelta(weeks=index)).isoformat(),
                "value": str(value),
            }
        )
    return rows


class BaselineTests(unittest.TestCase):
    def test_builds_normal_quantiles_from_ma3_and_historical_rmse(self):
        reference_date = date.fromisoformat("2025-10-12")
        forecasts, skipped = generate_round(
            round_rows(),
            reference_date=reference_date,
            data_cutoff=reference_date - timedelta(weeks=1),
            data_version="fixed-version",
        )
        self.assertEqual(skipped, [])
        self.assertEqual(len(forecasts), 4 * len(QUANTILES))
        horizon_zero = [row for row in forecasts if row["horizon"] == 0]
        self.assertEqual(
            tuple(float(row["output_type_id"]) for row in horizon_zero), QUANTILES
        )
        self.assertEqual({float(row["mean"]) for row in horizon_zero}, {39.0})
        self.assertTrue(all(float(row["value"]) >= 0 for row in horizon_zero))
        values = [float(row["value"]) for row in horizon_zero]
        self.assertEqual(values, sorted(values))
        # Linear data make the MA3 forecast two units below a horizon-0 outcome.
        self.assertTrue(math.isclose(float(horizon_zero[0]["standard_deviation"]), 2.0))

    def test_future_value_cannot_change_forecast(self):
        reference_date = date.fromisoformat("2025-10-12")
        base, _ = generate_round(
            round_rows(),
            reference_date=reference_date,
            data_cutoff=reference_date - timedelta(weeks=1),
            data_version="fixed-version",
        )
        changed, _ = generate_round(
            round_rows(changed_final_value=100000),
            reference_date=reference_date,
            data_cutoff=reference_date - timedelta(weeks=1),
            data_version="fixed-version",
        )
        self.assertEqual(base, changed)

    def test_requires_exact_weekly_cutoff(self):
        with self.assertRaisesRegex(ValueError, "one week"):
            generate_round(
                round_rows(),
                reference_date=date.fromisoformat("2025-10-12"),
                data_cutoff=date.fromisoformat("2025-10-12"),
                data_version="fixed-version",
            )

    def test_writes_dashboard_compatible_files(self):
        reference_date = date.fromisoformat("2025-10-12")
        forecasts, _ = generate_round(
            round_rows(),
            reference_date=reference_date,
            data_cutoff=reference_date - timedelta(weeks=1),
            data_version="fixed-version",
        )
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_hubverse_files(Path(temporary), forecasts)
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, f"2025-10-12-{MODEL_ID}.csv")
            with paths[0].open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(tuple(reader.fieldnames or ()), HUBVERSE_COLUMNS)
            self.assertEqual(len(rows), 4 * len(QUANTILES))


if __name__ == "__main__":
    unittest.main()
