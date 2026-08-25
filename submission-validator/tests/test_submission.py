from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from forecast_submission_validation.submission import validate_submission

from helpers import rows, write_metadata, write_schema, write_submission


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.metadata_root = self.root / "metadata"
        self.schema = self.root / "schema.json"
        write_metadata(self.metadata_root)
        write_schema(self.schema)

    def tearDown(self):
        self.temporary.cleanup()

    def validate(self, records, **kwargs):
        path = write_submission(self.root / "output", records)
        return validate_submission(
            path,
            metadata_root=self.metadata_root,
            schema_path=self.schema,
            **kwargs,
        )

    def test_complete_live_submission_passes(self):
        report = self.validate(rows(), submitted_at="2026-10-04T20:00:00+02:00")
        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.accepted_locations, ["SE", "SE-M", "SE-O"])

    def test_single_live_location_is_allowed(self):
        report = self.validate(rows(locations=("SE",)))
        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.accepted_locations, ["SE"])

    def test_invalid_location_does_not_reject_valid_location(self):
        records = rows(locations=("SE", "SE-M"))
        records[-1]["value"] = "not-a-number"
        report = self.validate(records)
        self.assertEqual(report.status, "PARTIAL")
        self.assertEqual(report.accepted_locations, ["SE"])
        self.assertEqual(report.rejected_locations, ["SE-M"])

    def test_missing_horizon_rejects_location(self):
        report = self.validate(rows(locations=("SE",))[:-1])
        self.assertEqual(report.status, "FAIL")
        self.assertIn("missing_horizon", {finding.check for finding in report.findings})

    def test_duplicate_horizon_rejects_location(self):
        records = rows(locations=("SE",))
        records.append(dict(records[-1]))
        report = self.validate(records)
        self.assertEqual(report.status, "FAIL")
        self.assertIn("duplicate_horizon", {finding.check for finding in report.findings})

    def test_historical_submission_requires_all_locations(self):
        records = rows(reference_date="2025-10-05", locations=("SE",))
        path = write_submission(
            self.root / "output",
            records,
            reference_date="2025-10-05",
        )
        report = validate_submission(
            path,
            metadata_root=self.metadata_root,
            schema_path=self.schema,
        )
        self.assertEqual(report.status, "FAIL")
        self.assertIn("missing_location", {finding.check for finding in report.findings})

    def test_historical_submission_rejects_an_invalid_location(self):
        records = rows(reference_date="2025-10-05")
        records[4]["value"] = "invalid"
        path = write_submission(
            self.root / "output",
            records,
            reference_date="2025-10-05",
        )
        report = validate_submission(
            path,
            metadata_root=self.metadata_root,
            schema_path=self.schema,
        )
        self.assertEqual(report.status, "FAIL")
        self.assertEqual(report.accepted_locations, ["SE", "SE-O"])

    def test_late_live_submission_fails(self):
        report = self.validate(rows(), submitted_at="2026-10-05T00:00:00+02:00")
        self.assertEqual(report.status, "FAIL")
        self.assertIn("deadline", {finding.check for finding in report.findings})

    def test_high_value_warns_but_passes(self):
        records = rows(locations=("SE",))
        records[0]["value"] = "100001"
        report = self.validate(records)
        self.assertEqual(report.status, "WARN")

    def test_negative_and_nonfinite_values_fail(self):
        for invalid in ("-1", "nan", "inf"):
            with self.subTest(invalid=invalid):
                records = rows(locations=("SE",))
                records[0]["value"] = invalid
                report = self.validate(records)
                self.assertEqual(report.status, "FAIL")


if __name__ == "__main__":
    unittest.main()
