from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from forecast_submission_validation.historical_batch import (
    create_template,
    split_and_validate,
)

from helpers import write_metadata, write_schema


class HistoricalBatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.metadata_root = self.root / "metadata"
        self.schema = self.root / "schema.json"
        write_metadata(self.metadata_root)
        write_schema(self.schema)
        self.reference_dates = [
            "2025-10-05",
            "2025-10-12",
        ]

    def tearDown(self):
        self.temporary.cleanup()

    def test_template_has_twelve_rows_per_round(self):
        path = self.root / "batch.csv"
        create_template(path, reference_dates=self.reference_dates)
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 24)

    def test_valid_batch_is_split_into_round_files(self):
        path = self.root / "batch.csv"
        create_template(path, reference_dates=self.reference_dates)
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fieldnames = reader.fieldnames
        for row in rows:
            row["value"] = "10"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        written = split_and_validate(
            path,
            model_id="team-model",
            reference_dates=self.reference_dates,
            metadata_root=self.metadata_root,
            schema_path=self.schema,
            output_root=self.root / "output",
        )
        self.assertEqual(len(written), 2)
        self.assertTrue(all(output.is_file() for output in written))

    def test_invalid_batch_is_not_written(self):
        path = self.root / "batch.csv"
        create_template(path, reference_dates=self.reference_dates)
        with self.assertRaises(ValueError):
            split_and_validate(
                path,
                model_id="team-model",
                reference_dates=self.reference_dates,
                metadata_root=self.metadata_root,
                schema_path=self.schema,
                output_root=self.root / "output",
            )
        self.assertFalse((self.root / "output").exists())


if __name__ == "__main__":
    unittest.main()
