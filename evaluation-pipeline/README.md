# Retrospective forecast matching

This package performs the first stages of retrospective evaluation. It reads
merged historical model submissions, joins every point forecast to the fixed
2025/2026 outcome, calculates individual-model point scores and fits the QRA
ensemble. Probabilistic QRA scoring is added separately.

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

## Score individual point forecasts

After matching, run:

```bash
score-retrospective-point-forecasts
```

The scoring command writes:

- `point-errors.csv`, with signed, absolute and squared error for every row;
- `point-metrics-by-location-horizon.csv`, with MAE, bias and RMSE separately
  for every model, location and horizon;
- `point-metrics-by-forecast-kind.csv`, comparing horizon-0 nowcasts with
  horizons 1–3 forecasts for every model and location;
- `point-score-report.json`, an audit summary explicitly recording that no
  ranking was created.

Bias is defined as `forecast_value - observed_value`: positive bias means
systematic overprediction and negative bias means systematic underprediction.
The output contains no overall model ranking.

## Build the retrospective QRA

The ensemble is LASSO Quantile Regression Averaging (LQRA): each individual
model forecast is a separate covariate, with an L1 penalty on model
coefficients and an unpenalized intercept. Run:

```bash
build-retrospective-qra
```

For every location and horizon, each historical QRA forecast is trained only
on outcomes that would already have been published by that forecast's
`reference_date`. At least eight such outcomes are required. The regularization
strength is selected separately for each quantile using expanding-window,
one-step-ahead pinball loss on the training data.

The seven quantiles 0.025, 0.1, 0.25, 0.5, 0.75, 0.9 and 0.975 define the
central 50%, 80% and 95% prediction intervals. Negative predictions are
truncated at zero. Quantiles are rearranged into monotone order when necessary,
and every adjustment is recorded.

The command writes:

- `qra-forecasts.csv`, with quantiles and training provenance;
- `qra-coefficients.csv`, with the fitted intercept and model coefficients;
- `qra-skipped-tasks.json`, listing early tasks with fewer than eight outcomes;
- `qra-report.json`, documenting the complete method and first usable round.

Method references:

- [Nowotarski and Weron (2015), *Computing electricity spot price prediction
  intervals using quantile regression and forecast averaging*](https://doi.org/10.1007/s00180-014-0523-0).
- [Uniejewski and Weron (2021), *Regularized quantile regression averaging for
  probabilistic electricity price forecasting*](https://doi.org/10.1016/j.eneco.2021.105121).

## Development tests

```bash
python -m unittest discover -s evaluation-pipeline/tests -v
```
