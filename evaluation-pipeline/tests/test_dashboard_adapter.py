from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from influenza_evaluation.dashboard_adapter import build_dashboard_view
from influenza_evaluation.qra import QUANTILES


def quantile_rows(reference_date: str = "2025-11-30") -> list[dict[str, str]]:
    return [
        {
            "reference_date": reference_date,
            "target_end_date": reference_date,
            "target": "weekly incident influenza cases",
            "horizon": "0",
            "location": "SE",
            "location_name": "Sverige",
            "output_type": "quantile",
            "output_type_id": str(quantile),
            "value": str(10 + quantile),
            "outcome_data_version": "fixed-version",
        }
        for quantile in QUANTILES
    ]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class DashboardAdapterTests(unittest.TestCase):
    def test_builds_complete_hubverse_demo_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            write_csv(inputs / "qra.csv", quantile_rows())
            write_csv(inputs / "baseline.csv", quantile_rows())
            write_csv(
                inputs / "outcomes.csv",
                [
                    {
                        "location": "SE",
                        "target_end_date": "2025-11-30",
                        "value": "12",
                    }
                ],
            )
            config = inputs / "hub-config"
            config.mkdir()
            (config / "admin.json").write_text("{}\n")
            (config / "model-metadata-schema.json").write_text("{}\n")
            metadata = inputs / "metadata"
            metadata.mkdir()
            (metadata / "hub-qra.yml").write_text("model_id: hub-qra\n")
            (metadata / "hub-normalma3.yml").write_text(
                "model_id: hub-normalma3\n"
            )

            output = root / "view"
            report = build_dashboard_view(
                output_root=output,
                qra_input=inputs / "qra.csv",
                baseline_input=inputs / "baseline.csv",
                outcomes_input=inputs / "outcomes.csv",
                hub_config_root=config,
                metadata_root=metadata,
            )

            self.assertEqual(report["models"], ["hub-qra", "hub-normalma3"])
            self.assertFalse(report["participant_submission_format_changed"])
            tasks = json.loads((output / "hub-config" / "tasks.json").read_text())
            model_task = tasks["rounds"][0]["model_tasks"][0]
            self.assertIn("target_end_date", model_task["task_ids"])
            self.assertEqual(
                model_task["output_type"]["quantile"]["output_type_id"]["required"],
                list(QUANTILES),
            )
            for model_id in ("hub-qra", "hub-normalma3"):
                path = (
                    output
                    / "model-output"
                    / model_id
                    / f"2025-11-30-{model_id}.csv"
                )
                with path.open(encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(len(rows), len(QUANTILES))
                self.assertIn("target_end_date", rows[0])
            self.assertTrue((output / "predtimechart-config.yml").exists())
            target_json = (
                output
                / "predtimechart-targets"
                / "weekly-incident-influenza-cases_SE_2025-11-30.json"
            )
            self.assertEqual(
                json.loads(target_json.read_text()),
                {"date": ["2025-11-30"], "y": [12.0]},
            )


if __name__ == "__main__":
    unittest.main()
