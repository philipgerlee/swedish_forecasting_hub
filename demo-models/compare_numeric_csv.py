"""Compare two CSV files, allowing insignificant floating-point differences."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def compare(expected_path: Path, actual_path: Path) -> None:
    with expected_path.open("r", encoding="utf-8-sig", newline="") as handle:
        expected = list(csv.reader(handle))
    with actual_path.open("r", encoding="utf-8-sig", newline="") as handle:
        actual = list(csv.reader(handle))

    if not expected or not actual or expected[0] != actual[0]:
        raise ValueError("CSV headers differ")
    if len(expected) != len(actual):
        raise ValueError(f"Row counts differ: {len(expected)} != {len(actual)}")

    for row_number, (expected_row, actual_row) in enumerate(
        zip(expected, actual, strict=True), start=1
    ):
        if len(expected_row) != len(actual_row):
            raise ValueError(f"Column counts differ on row {row_number}")
        for column_number, (expected_value, actual_value) in enumerate(
            zip(expected_row, actual_row, strict=True), start=1
        ):
            if expected_value == actual_value:
                continue
            try:
                expected_number = float(expected_value)
                actual_number = float(actual_value)
            except ValueError as exc:
                raise ValueError(
                    f"Text differs at row {row_number}, column {column_number}: "
                    f"{expected_value!r} != {actual_value!r}"
                ) from exc
            if not math.isclose(
                expected_number, actual_number, rel_tol=1e-9, abs_tol=1e-9
            ):
                raise ValueError(
                    f"Number differs at row {row_number}, column {column_number}: "
                    f"{expected_value} != {actual_value}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    args = parser.parse_args()
    compare(args.expected, args.actual)
    print(f"Equivalent: {args.expected} and {args.actual}")


if __name__ == "__main__":
    main()
