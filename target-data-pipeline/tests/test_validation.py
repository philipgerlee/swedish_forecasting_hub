import unittest

from influenza_target_data.transform import transform_dataset
from influenza_target_data.validate import validate_rows

from helpers import dataset


class ValidationTests(unittest.TestCase):
    def test_complete_week_passes(self):
        rows = [
            row
            for row in transform_dataset(dataset())
            if row["source_year_week"] == "2026W20"
        ]
        findings = validate_rows(rows, ["2026W20"], [])
        self.assertFalse([item for item in findings if item["severity"] != "warning"])

    def test_missing_region_is_incomplete(self):
        rows = [
            row
            for row in transform_dataset(dataset())
            if row["source_year_week"] == "2026W20"
            and row["source_region_code"] != "14"
        ]
        findings = validate_rows(rows, ["2026W20"], [])
        checks = {item["check"] for item in findings if item["severity"] == "incomplete"}
        self.assertIn("missing_region_week", checks)

    def test_negative_value_is_hard_failure(self):
        rows = [
            row
            for row in transform_dataset(dataset(values=[65, 53, 7, -1, 7, 2]))
            if row["source_year_week"] == "2026W20"
        ]
        findings = validate_rows(rows, ["2026W20"], [])
        self.assertIn("invalid_count", {item["check"] for item in findings})

    def test_frozen_value_cannot_change(self):
        rows = [
            row
            for row in transform_dataset(dataset())
            if row["source_year_week"] == "2026W20"
        ]
        existing = [
            {
                "location": "SE",
                "target_end_date": "2026-05-17",
                "value": "999",
                "source_region_code": "00",
                "source_year_week": "2026W20",
            }
        ]
        findings = validate_rows(rows, ["2026W20"], existing)
        self.assertIn("frozen_value_changed", {item["check"] for item in findings})

    def test_decline_over_half_is_warning(self):
        rows = [
            row
            for row in transform_dataset(dataset())
            if row["source_year_week"] == "2026W20"
        ]
        existing = [
            {
                "location": "SE",
                "target_end_date": "2026-05-10",
                "value": "200",
                "source_region_code": "00",
                "source_year_week": "2026W19",
            }
        ]
        findings = validate_rows(rows, ["2026W20"], existing)
        self.assertIn("large_weekly_decline", {item["check"] for item in findings})


if __name__ == "__main__":
    unittest.main()
