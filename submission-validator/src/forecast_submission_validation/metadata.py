"""Load and validate one model metadata document."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class MetadataError(ValueError):
    """Raised when model metadata is absent or invalid."""


def load_metadata(
    model_id: str,
    metadata_root: Path,
    schema_path: Path,
) -> dict[str, Any]:
    path = metadata_root / f"{model_id}.yml"
    if not path.is_file():
        raise MetadataError(f"Missing metadata file: {path}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MetadataError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise MetadataError(f"Metadata in {path} must be a YAML object")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        details = []
        for error in errors:
            field = ".".join(str(part) for part in error.absolute_path) or "document"
            details.append(f"{field}: {error.message}")
        raise MetadataError("; ".join(details))

    expected = f"{document['team_abbr']}-{document['model_abbr']}"
    if document["model_id"] != expected:
        raise MetadataError(
            f"model_id {document['model_id']!r} must equal team_abbr-model_abbr "
            f"({expected!r})"
        )
    if document["model_id"] != model_id:
        raise MetadataError(
            f"Metadata model_id {document['model_id']!r} does not match {model_id!r}"
        )
    if document.get("code_repository") and not document.get("code_license"):
        raise MetadataError("code_license is required when code_repository is public")
    return document
