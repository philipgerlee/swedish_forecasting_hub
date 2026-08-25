# Demonstration models

The hub retains six simple baseline models and their forecasts as a permanent
public demonstration of the retrospective workflow, evaluation and QRA
ensemble. They are hub-operated examples, not participant submissions or
recommended epidemiological models.

All models use only the target data supplied for a forecast round. Each of the
three locations is modelled independently; information is never pooled across
locations. For horizon 0--3, the models forecast one through four weeks beyond
the latest observation available at the round's cutoff.

| Model ID | Forecast rule |
| --- | --- |
| `hubdemo-persistence` | Repeat the latest observed value. |
| `hubdemo-mean3` | Mean of the latest three observations. |
| `hubdemo-mean6` | Mean of the latest six observations. |
| `hubdemo-linear4` | Ordinary linear trend fitted to the latest four observations. |
| `hubdemo-damped4` | Four-observation linear trend, damped by a factor of 0.8 per forecast step. |
| `hubdemo-exptrend4` | Linear trend fitted to `log(1 + value)` for the latest four observations and transformed back. |

Negative trend extrapolations are truncated at zero. The implementation uses
only the Python standard library. Regenerate or verify the 33 retrospective
rounds from the repository root with:

```bash
python demo-models/generate_demo_forecasts.py
python demo-models/generate_demo_forecasts.py --check
```

The committed forecasts use the ordinary `model-output/<model_id>/` layout and
their public descriptions use the ordinary `model-metadata/<model_id>.yml`
layout. A future website can therefore display and evaluate them through the
same interface used for participant models.
