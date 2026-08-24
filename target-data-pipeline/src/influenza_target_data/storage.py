"""Read and atomically update the frozen target-data CSV."""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .config import OUTPUT_COLUMNS


class StorageError(RuntimeError):
    """Raised when the public target-data file violates its schema."""


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
            raise StorageError(
                "Target-data columns do not match the required schema: "
                f"{reader.fieldnames!r}"
            )
        rows = list(reader)
    for line_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise StorageError(f"Malformed target-data row at line {line_number}")
    return rows


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["location"]), str(row["target_end_date"])


def new_rows_only(
    existing: Iterable[dict[str, Any]], candidates: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    existing_by_key = {row_key(row): row for row in existing}
    return [row for row in candidates if row_key(row) not in existing_by_key]


def write_rows_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row[column] for column in OUTPUT_COLUMNS})
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
