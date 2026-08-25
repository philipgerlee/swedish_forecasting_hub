# Model submissions and validation

This is the normative technical guide for individual model submissions to the
Swedish Influenza Forecast Hub pilot. Forecasts are submitted through a GitHub
pull request. Only the hub operator merges submissions into `main`.

## 1. Register a model

Choose a permanent model identifier in the form `<team_abbr>-<model_abbr>`.
Each abbreviation may contain letters, digits, underscores and `+`, and may be
at most 16 characters. Do not reuse an identifier for a different method.

Copy `templates/model-metadata-template.yml` to:

```text
model-metadata/<model_id>.yml
```

Public model code is optional. When `code_repository` is supplied,
`code_license` is required. Forecast output is licensed CC BY 4.0.

## 2. Create a forecast file

Copy `templates/model-output-template.csv` to:

```text
model-output/<model_id>/YYYY-MM-DD-<model_id>.csv
```

`YYYY-MM-DD` is the Sunday `reference_date`. One row represents one point
forecast. The columns must appear in this exact order:

```text
reference_date,target,horizon,location,output_type,output_type_id,value
```

- `target`: `weekly incident influenza cases`
- `horizon`: `0`, `1`, `2`, or `3`; the target week ends on
  `reference_date + 7 × horizon days`
- `location`: `SE`, `SE-M`, or `SE-O`
- `output_type`: `mean`
- `output_type_id`: empty or `NA`
- `value`: the model's expected number of reported cases; finite and at least 0

For every submitted location, all four horizons are required exactly once. A
live model may submit one, two, or three locations. Historical submissions for
2025/2026 must contain all three locations.

## 3. Validate locally

With Python 3.11 or later:

```bash
python -m pip install -e submission-validator
validate-model-metadata model-metadata/<model_id>.yml
validate-forecast-submission model-output/<model_id>/<file>.csv
```

The repository also includes dependency-free helpers for creating files in
Python or R and a base-R forecast validator:

```bash
python submission-tools/create_submission.py YYYY-MM-DD team-model
Rscript submission-tools/create_submission.R YYYY-MM-DD team-model
Rscript submission-tools/validate_submission.R model-output/<model_id>/<file>.csv
```

### Editable model starter programs

Participants who want the program to create a completed forecast file can copy
and edit either:

- `submission-tools/model_template.py`
- `submission-tools/model_template.R`

Replace only the clearly marked `forecast_model` function with the model code.
The function receives the available target data and the requested
`reference_date`, and returns `location`, `horizon` and `value`. The surrounding
program checks the result and writes the required columns, path and filename.

Run the Python or R version from the repository root:

```bash
python submission-tools/model_template.py YYYY-MM-DD team-model
Rscript submission-tools/model_template.R YYYY-MM-DD team-model
```

For a 2025/2026 retrospective date, the program automatically reads the
corresponding fixed round file. For a live date, it reads
`target-data/time-series.csv`. In both cases, observations after
`reference_date - 7 days` are removed before the participant model is called.
The included function is only a working persistence-model example and should
be replaced with the participant's model.

After replacing the function, generate all 33 retrospective submissions in one
batch with either command:

```bash
python submission-tools/model_template.py --all-historical team-model
Rscript submission-tools/model_template.R --all-historical team-model
```

The round dates are read from the committed manifest and processed
chronologically. All rounds are run and checked before any files are written,
so a failed model run does not leave a partial batch. Successful output is
written directly to `model-output/team-model/`.

The validator reports accepted and rejected locations separately. A technically
valid value above 100,000 is accepted with a manual-review warning.

## 4. Submit in a browser without Git commands

1. Sign in to GitHub and open the hub repository.
2. Select **Fork** to create a copy under your account.
3. In the fork, use **Add file → Create new file** or **Upload files**.
4. Add the metadata YAML at `model-metadata/<model_id>.yml`.
5. Add the forecast CSV at
   `model-output/<model_id>/YYYY-MM-DD-<model_id>.csv`.
6. Select **Contribute → Open pull request**.
7. Read the automatic validation report. Correct the files in the same pull
   request until the checks pass or only an expected partial-location warning
   remains.

Submissions close Sunday at 23:59 Europe/Stockholm. Corrections may be made
without limit before the deadline. The last valid version committed before the
deadline is the official submission.

## Validation outcomes

- `PASS`: all submitted locations are complete and valid.
- `WARN`: all locations are valid, with a value requiring manual review.
- `PARTIAL`: at least one location is valid and at least one is rejected. Only
  accepted locations may be used downstream.
- `FAIL`: a file-level requirement failed or no location is valid.

GitHub Actions repeats these checks on every pull request that changes model
output or metadata. Forecast files and metadata must not be deleted through a
participant pull request.

## Historical forecasts for 2025/2026

The retrospective exercise contains 33 rounds from ISO week 40 of 2025 through
week 20 of 2026. For each manifest row, run the unchanged model with the named
input file and its `reference_date`. Every historical round must contain all
three locations and horizons 0–3.

Participants not using the editable model starter may instead collect all 396
rows in one CSV before creating the 33 standard HubVerse files. Create a blank
batch template with Python or R:

```bash
python submission-tools/prepare_historical_submission.py template team-model
Rscript submission-tools/create_historical_submission.R team-model
```

After filling the `value` column, validate and split the batch:

```bash
python submission-tools/prepare_historical_submission.py split historical-2025-2026-team-model.csv team-model
Rscript submission-tools/split_historical_submission.R historical-2025-2026-team-model.csv team-model
```

The resulting 33 files are written to `model-output/team-model/`. Upload the
whole directory and the model metadata file in one pull request. GitHub accepts
up to 100 files in one browser upload, so no round-by-round upload is needed.
