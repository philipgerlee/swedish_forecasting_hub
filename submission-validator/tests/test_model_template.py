from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from forecast_submission_validation.submission import validate_submission


class ModelTemplateTests(unittest.TestCase):
    def run_template(self, repository: Path, output: Path, *extra: str):
        return subprocess.run(
            [
                sys.executable,
                "submission-tools/model_template.py",
                "2025-10-05",
                "example-example",
                "--output",
                str(output),
                *extra,
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_python_template_writes_a_valid_historical_submission(self):
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            output = (
                Path(temporary)
                / "example-example"
                / "2025-10-05-example-example.csv"
            )
            result = self.run_template(repository, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = validate_submission(
                output,
                metadata_root=repository / "examples/model-metadata",
                schema_path=repository / "hub-config/model-metadata-schema.json",
            )
            self.assertEqual(report.status, "PASS", report.as_dict())
            self.assertEqual(report.accepted_locations, ["SE", "SE-M", "SE-O"])

    def test_python_template_removes_data_after_the_cutoff(self):
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            input_path = temporary_root / "input.csv"
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("location", "target_end_date", "value", "status"),
                )
                writer.writeheader()
                for location in ("SE", "SE-M", "SE-O"):
                    writer.writerow(
                        {
                            "location": location,
                            "target_end_date": "2025-09-28",
                            "value": "1",
                            "status": "available",
                        }
                    )
                    writer.writerow(
                        {
                            "location": location,
                            "target_end_date": "2025-10-05",
                            "value": "999",
                            "status": "available",
                        }
                    )
            output = (
                temporary_root
                / "example-example"
                / "2025-10-05-example-example.csv"
            )
            result = self.run_template(
                repository,
                output,
                "--input-data",
                str(input_path),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with output.open(encoding="utf-8", newline="") as handle:
                values = {row["value"] for row in csv.DictReader(handle)}
            self.assertEqual(values, {"1.0"})

    def test_python_template_writes_all_historical_rounds_in_batch_mode(self):
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [
                    sys.executable,
                    "submission-tools/model_template.py",
                    "--all-historical",
                    "example-example",
                    "--output-root",
                    temporary,
                ],
                cwd=repository,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs = sorted((Path(temporary) / "example-example").glob("*.csv"))
            self.assertEqual(len(outputs), 33)
            self.assertEqual(
                outputs[0].name,
                "2025-10-05-example-example.csv",
            )
            self.assertEqual(
                outputs[-1].name,
                "2026-05-17-example-example.csv",
            )
            for output in outputs:
                report = validate_submission(
                    output,
                    metadata_root=repository / "examples/model-metadata",
                    schema_path=repository / "hub-config/model-metadata-schema.json",
                )
                self.assertEqual(report.status, "PASS", report.as_dict())


if __name__ == "__main__":
    unittest.main()
