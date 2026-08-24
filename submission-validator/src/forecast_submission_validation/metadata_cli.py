"""Validate one or more public model metadata YAML files."""

from __future__ import annotations

import argparse
from pathlib import Path

from .metadata import MetadataError, load_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("hub-config/model-metadata-schema.json"),
    )
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        model_id = path.stem
        try:
            load_metadata(model_id, path.parent, args.schema)
            print(f"PASS: {path}")
        except (MetadataError, OSError) as exc:
            failed = True
            print(f"FAIL: {path}\n  ERROR metadata: {exc}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
