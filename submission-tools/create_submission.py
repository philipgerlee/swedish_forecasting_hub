"""Create a 12-row CSV submission template using only the Python standard library."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

COLUMNS = (
    "reference_date",
    "target",
    "horizon",
    "location",
    "output_type",
    "output_type_id",
    "value",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_date")
    parser.add_argument("model_id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reference_date = date.fromisoformat(args.reference_date)
    if reference_date.weekday() != 6:
        parser.error("reference_date must be a Sunday")
    output = args.output or (
        Path("model-output")
        / args.model_id
        / f"{reference_date.isoformat()}-{args.model_id}.csv"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for location in ("SE", "SE-M", "SE-O"):
            for horizon in range(4):
                writer.writerow(
                    {
                        "reference_date": reference_date.isoformat(),
                        "target": "weekly incident influenza cases",
                        "horizon": horizon,
                        "location": location,
                        "output_type": "mean",
                        "output_type_id": "",
                        "value": "",
                    }
                )
    print(output)


if __name__ == "__main__":
    main()
