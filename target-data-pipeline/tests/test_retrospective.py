import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from influenza_target_data.retrospective import (
    ROUND_END,
    ROUND_START,
    canonical_rows,
    round_reference_dates,
    source_weeks_through,
    write_manifest,
)


class RetrospectiveTests(unittest.TestCase):
    def test_rounds_are_week_40_through_week_20(self):
        rounds = round_reference_dates()
        self.assertEqual(len(rounds), 33)
        self.assertEqual(rounds[0], ROUND_START)
        self.assertEqual(rounds[-1], ROUND_END)

    def test_source_weeks_are_cut_by_target_end_date(self):
        metadata = {
            "variables": [
                {
                    "code": "År och vecka",
                    "values": ["2025W38", "2025W39", "2025W40"],
                }
            ]
        }
        self.assertEqual(
            source_weeks_through(metadata, date.fromisocalendar(2025, 39, 7)),
            ["2025W38", "2025W39"],
        )

    def test_canonical_rows_match_prospective_schema_values(self):
        rows = canonical_rows(
            [
                {
                    "source_region_code": "00",
                    "source_year_week": "2025W39",
                    "value": 12,
                    "status": "available",
                }
            ],
            data_version="2026-08-25T00:00:00Z",
        )
        self.assertEqual(rows[0]["location"], "SE")
        self.assertEqual(rows[0]["target_end_date"], "2025-09-28")
        self.assertEqual(rows[0]["release_status"], "historical")

    def test_manifest_has_one_self_contained_file_per_round(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.csv"
            records = write_manifest(path, "2026-08-25T00:00:00Z")
            self.assertEqual(len(records), 33)
            self.assertEqual(records[0]["data_cutoff"], "2025-09-28")
            self.assertEqual(records[-1]["data_cutoff"], "2026-05-10")
            with path.open(encoding="utf-8", newline="") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 33)


if __name__ == "__main__":
    unittest.main()
