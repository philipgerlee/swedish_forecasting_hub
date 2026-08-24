import unittest

from influenza_target_data.fetch import SourceError, build_query, validate_metadata
from influenza_target_data.transform import transform_dataset

from helpers import dataset, metadata


class FetchTransformTests(unittest.TestCase):
    def test_query_uses_current_table_dimensions(self):
        query = build_query(["2026W20"])
        selections = {item["code"]: item["selection"]["values"] for item in query["query"]}
        self.assertEqual(selections["Region"], ["00", "12", "14"])
        self.assertEqual(selections["Typ av influensa"], ["1+2"])
        self.assertEqual(selections["Mått"], ["1"])
        self.assertEqual(selections["Kön"], ["1+2+0"])

    def test_metadata_rejects_missing_required_code(self):
        value = metadata()
        next(item for item in value["variables"] if item["code"] == "Kön")["values"] = ["1"]
        with self.assertRaises(SourceError):
            validate_metadata(value)

    def test_transform_respects_jsonstat_dimension_order(self):
        rows = transform_dataset(dataset())
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            rows[0],
            {
                "source_region_code": "00",
                "source_region_label": "Riket",
                "source_year_week": "2026W19",
                "value": 65,
                "status": "available",
            },
        )
        self.assertEqual(rows[-1]["source_region_code"], "14")
        self.assertEqual(rows[-1]["source_year_week"], "2026W20")

    def test_pxweb_nil_symbol_is_exact_zero(self):
        rows = transform_dataset(dataset(values=[65, 53, 7, None, 7, 2], statuses={"3": "-"}))
        self.assertEqual(rows[3]["status"], "available")
        self.assertEqual(rows[3]["value"], 0)

    def test_other_null_value_is_missing(self):
        rows = transform_dataset(dataset(values=[65, 53, 7, None, 7, 2], statuses={"3": "."}))
        self.assertEqual(rows[3]["status"], "missing")
        self.assertIsNone(rows[3]["value"])


if __name__ == "__main__":
    unittest.main()
