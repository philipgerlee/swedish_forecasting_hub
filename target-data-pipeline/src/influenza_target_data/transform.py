"""Transform a JSON-stat2 data cube into target-data rows."""

from __future__ import annotations

from itertools import product
from math import prod
from typing import Any, Iterator

from .config import TIME_DIMENSION


class TransformError(RuntimeError):
    """Raised when the JSON-stat2 dataset cannot be interpreted safely."""


def _ordered_codes(dimension: dict[str, Any]) -> list[str]:
    category = dimension.get("category", {})
    index = category.get("index")
    if isinstance(index, dict):
        return [code for code, _ in sorted(index.items(), key=lambda item: item[1])]
    if isinstance(index, list):
        return list(index)
    raise TransformError("JSON-stat2 category index is missing or invalid")


def _indexed_value(container: Any, index: int) -> Any:
    if isinstance(container, list):
        return container[index] if index < len(container) else None
    if isinstance(container, dict):
        return container.get(str(index), container.get(index))
    return None


def _status(value: Any, source_status: Any) -> str:
    if value is not None or source_status == "-":
        return "available"
    if source_status in {"c", "confidential", "..", "..."}:
        return "suppressed"
    return "missing"


def cube_records(dataset: dict[str, Any]) -> Iterator[dict[str, Any]]:
    ids = dataset.get("id")
    sizes = dataset.get("size")
    dimensions = dataset.get("dimension")
    if not isinstance(ids, list) or not isinstance(sizes, list):
        raise TransformError("JSON-stat2 id or size is missing")
    if len(ids) != len(sizes) or not isinstance(dimensions, dict):
        raise TransformError("JSON-stat2 dimensions are inconsistent")

    codes_by_dimension = []
    labels_by_dimension: dict[str, dict[str, str]] = {}
    for dimension_id, size in zip(ids, sizes):
        if dimension_id not in dimensions:
            raise TransformError(f"Missing JSON-stat2 dimension {dimension_id!r}")
        codes = _ordered_codes(dimensions[dimension_id])
        if len(codes) != size:
            raise TransformError(f"Size mismatch for dimension {dimension_id!r}")
        codes_by_dimension.append(codes)
        labels_by_dimension[dimension_id] = dimensions[dimension_id].get(
            "category", {}
        ).get("label", {})

    expected_values = prod(sizes)
    values = dataset.get("value")
    if isinstance(values, list) and len(values) != expected_values:
        raise TransformError(
            f"Expected {expected_values} values but received {len(values)}"
        )
    statuses = dataset.get("status", {})

    for flat_index, combination in enumerate(product(*codes_by_dimension)):
        record = dict(zip(ids, combination))
        record["_value"] = _indexed_value(values, flat_index)
        record["_status"] = _indexed_value(statuses, flat_index)
        record["_labels"] = {
            dimension_id: labels_by_dimension[dimension_id].get(code, code)
            for dimension_id, code in zip(ids, combination)
        }
        yield record


def transform_dataset(dataset: dict[str, Any] | None) -> list[dict[str, Any]]:
    if dataset is None:
        return []
    required = {"Region", TIME_DIMENSION}
    ids = set(dataset.get("id", []))
    missing = sorted(required - ids)
    if missing:
        raise TransformError(f"Dataset is missing dimensions {missing}")

    rows: list[dict[str, Any]] = []
    for record in cube_records(dataset):
        value = record["_value"]
        # PC-Axis/PxWeb uses the NIL symbol "-" for an exact zero. JSON-stat2
        # carries that as null plus a status code, so this is source decoding,
        # not imputation.
        if value is None and record["_status"] == "-":
            value = 0
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        rows.append(
            {
                "source_region_code": record["Region"],
                "source_region_label": record["_labels"]["Region"],
                "source_year_week": record[TIME_DIMENSION],
                "value": value,
                "status": _status(value, record["_status"]),
            }
        )
    return rows
