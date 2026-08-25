# Target-data pipeline

This package fetches weekly influenza observations from Folkhälsodata,
validates them and appends new frozen values to `target-data/time-series.csv`.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e target-data-pipeline
python -m unittest discover -s target-data-pipeline/tests -v
```

Run a dry run for a specific ISO week:

```bash
update-influenza-target-data --target-week 2026W20 --dry-run
```

Without `--target-week`, the pipeline identifies unpublished weeks in the
current week-30-to-week-20 data season. Forecast rounds can still begin in week
40; weeks 30--39 provide calibration data. The detailed validation report is written to
`validation-report.json`. A short Markdown summary is written to
`validation-summary.md`.

The GitHub Actions workflow can also be started manually with an explicit
target week. This is the deliberately simple mechanism for extending a season
beyond week 20 when needed.

The automated weekly workflow validates incoming data but does not rerun the
software development test suite. Development tests run when pipeline code is
changed.

## Retrospective 2025/2026 data

The fixed retrospective package contains one self-contained input file per
forecast round, from ISO week 40 of 2025 through week 20 of 2026, plus final
outcomes through week 23. Build it from Folkhälsodata with a fixed version
timestamp:

```bash
build-retrospective-influenza-data --data-version 2026-08-25T00:00:00Z
```

The committed files can be checked without contacting Folkhälsodata:

```bash
build-retrospective-influenza-data --verify-only
```

See [`retrospective-data/2025-2026/README.md`](../retrospective-data/2025-2026/README.md)
for the manifest and participant-use rules.
