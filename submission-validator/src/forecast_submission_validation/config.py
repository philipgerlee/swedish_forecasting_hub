"""Normative constants from the hub technical specification."""

from __future__ import annotations

from datetime import date

COLUMNS = (
    "reference_date",
    "target",
    "horizon",
    "location",
    "output_type",
    "output_type_id",
    "value",
)

TARGET = "weekly incident influenza cases"
LOCATIONS = ("SE", "SE-M", "SE-O")
HORIZONS = (0, 1, 2, 3)
OUTPUT_TYPE = "mean"
HIGH_VALUE_WARNING = 100_000

HISTORICAL_START = date.fromisocalendar(2025, 40, 7)
HISTORICAL_END = date.fromisocalendar(2026, 20, 7)
LIVE_START = date.fromisocalendar(2026, 40, 7)
LIVE_END = date.fromisocalendar(2027, 20, 7)
