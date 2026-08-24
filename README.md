# Swedish Forecasting Hub

Research pilot for weekly influenza forecasts in Sweden, Region Skåne and
Västra Götaland.

The repository is being built around the [hubverse](https://hubverse.io/)
conventions. The first operational component is the target-data pipeline:

- `target-data/time-series.csv` contains frozen weekly observations.
- `target-data-pipeline/` fetches, transforms and validates data from
  Folkhälsodata.
- `.github/workflows/` contains development tests and the scheduled data
  update workflow.

Forecast-submission and ensemble components will be added separately.
