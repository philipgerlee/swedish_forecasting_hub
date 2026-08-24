# Influenza target data

`time-series.csv` contains weekly reported influenza cases for Sweden, Region
Skåne and Västra Götaland. Values are fetched from Folkhälsodata and frozen at
the first complete successful release observed by the hub.

## Source

- Table: `binflRegtid.px`
- Measure: reported cases (`Mått = 1`)
- Influenza type: total (`Typ av influensa = 1+2`)
- Sex: total (`Kön = 1+2+0`)
- Regions: Sweden (`00`), Skåne (`12`) and Västra Götaland (`14`)

The pipeline starts freezing values with ISO week 30 of the 2026/2027 data
season. Weeks 30--39 provide calibration data; this does not change the planned
start of forecast rounds in week 40. At the initial collection, already
published weeks use the values then available from the same Folkhälsodata table
and are marked `delayed_release`. No additional correction handling is applied.

`target_end_date` is the Sunday of the corresponding ISO week. Later source
revisions do not overwrite a value already frozen by the hub. Corrections are
made only when the hub's own extraction or transformation was wrong, using a
transparent Git commit.

PxWeb's NIL status symbol (`-`) means an exact zero and is therefore written as
`value = 0`. Other unavailable or protected source values are not converted or
imputed.

## Release status

- `on_time`: published during the normal release window for that target week.
- `delayed_release`: added after the forecast round for that week was cancelled.
