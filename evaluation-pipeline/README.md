# Retrospective forecast matching

This package performs the first stage of retrospective evaluation. It reads
merged historical model submissions and joins every point forecast to the fixed
2025/2026 outcome. It does not calculate scores or fit the QRA ensemble.

The matching rule is:

```text
target_end_date = reference_date + 7 × horizon days
```

Thus, horizon 0 is the ISO week ending on `reference_date`, while horizon 3
ends three Sundays later. The final week-20 round therefore uses outcomes
through ISO week 23.

## Run locally

```bash
python -m pip install -e evaluation-pipeline
match-retrospective-forecasts
```

The command discovers historical CSV files under `model-output/`, verifies that
each model has all 33 rounds and each file contains all three locations and
horizons 0–3, and writes:

- `evaluation-output/2025-2026/matched-forecasts.csv`
- `evaluation-output/2025-2026/match-report.json`

No output is written if a forecast is incomplete, invalid or lacks a final
outcome. Before participant forecasts have been merged, `--allow-empty` can be
used to create header-only artifacts.

## Development tests

```bash
python -m unittest discover -s evaluation-pipeline/tests -v
```
