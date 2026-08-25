# Retrospective round data for 2025/2026

This directory contains the fixed input data for the retrospective forecasting
exercise.

- `manifest.csv` defines the 33 Sunday forecast rounds from ISO week 40 of 2025
  through ISO week 20 of 2026.
- `rounds/YYYY-MM-DD.csv` is the self-contained model input for one round. It
  contains the available Folkhälsodata history through the Sunday before the
  `reference_date` and uses the same columns as `target-data/time-series.csv`.
- `final-outcomes.csv` contains the evaluation outcomes from week 40 of 2025
  through week 23 of 2026. Weeks 21–23 are included to evaluate horizons 1–3
  from the final week-20 forecast round.

All files use the fixed data version `2026-08-25T00:00:00Z`. Participants must
process rounds chronologically and use only the input file named in the current
manifest row.

Regenerate the package from Folkhälsodata:

```bash
python -m pip install -e target-data-pipeline
build-retrospective-influenza-data --data-version 2026-08-25T00:00:00Z
```

Verify the committed package without network access:

```bash
build-retrospective-influenza-data --verify-only
```
