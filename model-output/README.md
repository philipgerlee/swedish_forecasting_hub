# Model output

Submit one CSV file per model and forecast round:

```text
model-output/<model_id>/YYYY-MM-DD-<model_id>.csv
```

The date is the Sunday `reference_date`. See
[`docs/model-submissions.md`](../docs/model-submissions.md) for the complete
format and submission instructions.

Only forecast CSV files belong in this directory. Model code and documentation
must be stored elsewhere.
