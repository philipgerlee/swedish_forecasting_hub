from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from forecast_submission_validation.config import COLUMNS, HORIZONS, LOCATIONS, TARGET


def write_schema(path: Path) -> None:
    source = (
        Path(__file__).parents[2] / "hub-config" / "model-metadata-schema.json"
    )
    path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def write_metadata(root: Path, model_id: str = "team-model") -> None:
    root.mkdir(parents=True, exist_ok=True)
    team, model = model_id.split("-", 1)
    document = {
        "model_id": model_id,
        "team_name": "Team",
        "team_abbr": team,
        "model_name": "Model",
        "model_abbr": model,
        "model_version": "1.0.0",
        "model_contributors": [{"name": "A", "affiliation": "B"}],
        "methods": "A test model",
        "method_category": "statistical",
        "data_sources": ["Hub target data"],
        "software": ["Python"],
        "code_repository": None,
        "code_license": None,
        "license": "CC-BY-4.0",
        "designated_model": True,
    }
    (root / f"{model_id}.yml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )


def rows(
    reference_date: str = "2026-10-04",
    locations: tuple[str, ...] = LOCATIONS,
) -> list[dict[str, str]]:
    return [
        {
            "reference_date": reference_date,
            "target": TARGET,
            "horizon": str(horizon),
            "location": location,
            "output_type": "mean",
            "output_type_id": "",
            "value": str(10 + horizon),
        }
        for location in locations
        for horizon in HORIZONS
    ]


def write_submission(
    root: Path,
    records: list[dict[str, str]],
    *,
    model_id: str = "team-model",
    reference_date: str = "2026-10-04",
) -> Path:
    directory = root / model_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{reference_date}-{model_id}.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    return path
