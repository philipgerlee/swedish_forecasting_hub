"""Validate HubVerse configuration files against their declared schemas."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            schema_url = document["schema_version"]
            with urllib.request.urlopen(schema_url, timeout=30) as response:
                schema = json.load(response)
            errors = sorted(
                Draft202012Validator(schema).iter_errors(document),
                key=lambda error: list(error.absolute_path),
            )
            if errors:
                failed = True
                print(f"FAIL: {path}")
                for error in errors:
                    field = ".".join(str(part) for part in error.absolute_path)
                    print(f"  ERROR {field or 'document'}: {error.message}")
            else:
                print(f"PASS: {path}")
        except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
            failed = True
            print(f"FAIL: {path}\n  ERROR config: {exc}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
