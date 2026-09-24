import tempfile
import unittest
from pathlib import Path

from influenza_target_data.storage import load_rows, write_rows_atomic


def target_row(target_end_date: str, source_region_code: str) -> dict[str, object]:
    year, month, day = (int(part) for part in target_end_date.split("-"))
    location_by_source = {"00": "SE", "12": "SE-M", "14": "SE-O"}
    location = location_by_source[source_region_code]
    return {
        "location": location,
        "location_name": location,
        "year": year,
        "week": 1,
        "target_end_date": f"{year:04d}-{month:02d}-{day:02d}",
        "value": 1,
        "status": "available",
        "release_status": "on_time",
        "data_version": "2026-09-24T00:00:00Z",
        "source_region_code": source_region_code,
        "source_year_week": "2026W01",
        "official_release_time": "2026-09-24T00:00:00Z",
    }


class StorageTests(unittest.TestCase):
    def test_write_rows_sorts_by_week_then_location(self):
        rows = [
            target_row("2026-09-13", "14"),
            target_row("2026-09-06", "12"),
            target_row("2026-09-13", "00"),
            target_row("2026-09-06", "00"),
        ]

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "time-series.csv"
            write_rows_atomic(path, rows)
            written = load_rows(path)

        self.assertEqual(
            [
                (row["target_end_date"], row["source_region_code"])
                for row in written
            ],
            [
                ("2026-09-06", "00"),
                ("2026-09-06", "12"),
                ("2026-09-13", "00"),
                ("2026-09-13", "14"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
