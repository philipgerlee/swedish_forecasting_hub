from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from forecast_submission_validation.metadata import MetadataError, load_metadata

from helpers import write_metadata, write_schema


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.metadata_root = self.root / "metadata"
        self.schema = self.root / "schema.json"
        write_metadata(self.metadata_root)
        write_schema(self.schema)

    def tearDown(self):
        self.temporary.cleanup()

    def test_valid_metadata(self):
        document = load_metadata("team-model", self.metadata_root, self.schema)
        self.assertEqual(document["model_version"], "1.0.0")

    def test_model_id_must_match_components(self):
        path = self.metadata_root / "team-model.yml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["team_abbr"] = "other"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")
        with self.assertRaises(MetadataError):
            load_metadata("team-model", self.metadata_root, self.schema)

    def test_public_code_requires_license(self):
        path = self.metadata_root / "team-model.yml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["code_repository"] = "https://example.org/model"
        path.write_text(yaml.safe_dump(document), encoding="utf-8")
        with self.assertRaises(MetadataError):
            load_metadata("team-model", self.metadata_root, self.schema)


if __name__ == "__main__":
    unittest.main()
