# Swedish Forecasting Hub

Research pilot for weekly influenza forecasts in Sweden, Region Skåne and
Västra Götaland.

The repository follows [hubverse](https://hubverse.io/) directory and file
conventions. The operational components currently include:

- `target-data/time-series.csv` contains frozen weekly observations.
- `target-data-pipeline/` fetches, transforms and validates data from
  Folkhälsodata.
- `hub-config/` defines the modeling task and public model metadata schema.
- `model-output/` and `model-metadata/` receive participant submissions.
- `submission-validator/` validates forecasts, metadata and deadlines.
- `.github/workflows/` runs development tests, the scheduled data update and
  pull-request validation.

Participant instructions are available in
[`docs/model-submissions.md`](docs/model-submissions.md), with a Swedish quick
guide in [`docs/model-submissions-sv.md`](docs/model-submissions-sv.md).

The QRA ensemble, scoring and public visualization components will be added
separately.
