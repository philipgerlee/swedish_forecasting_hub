# Modellinlämning – snabbguide

Den engelska guiden `docs/model-submissions.md` är normerande. Detta är en kort
svensk sammanfattning.

1. Välj ett permanent `model_id` i formen `team-model`.
2. Kopiera metadatamallen till `model-metadata/<model_id>.yml`.
3. Kopiera CSV-mallen till
   `model-output/<model_id>/YYYY-MM-DD-<model_id>.csv`.
4. Ange söndagens datum som `reference_date` och lämna horisont 0–3 för varje
   plats som modellen deltar med.
5. Öppna en pull request senast söndag 23.59 Europe/Stockholm.
6. Läs den automatiska rapporten och rätta eventuella fel före tidsfristen.

En liveprognos får omfatta en, två eller tre platser. Historiska prognoser måste
omfatta Sverige, Region Skåne och Västra Götalandsregionen. Fel på en plats
utesluter den platsen men behöver inte ogiltigförklara övriga kompletta platser.

Inlämning kan göras helt i GitHubs webbläsare genom att forka repositoriet,
ladda upp filerna och välja **Contribute → Open pull request**.

## Redigerbara modellskal

Filerna `submission-tools/model_template.py` och
`submission-tools/model_template.R` är kompletta skalprogram. Deltagaren
ersätter endast den tydligt markerade funktionen `forecast_model` med sin egen
modellkod. Funktionen får tillgängliga måldata och aktuellt `reference_date`
och ska returnera `location`, `horizon` och `value`.

Kör önskad version från repositoriets rotkatalog:

```bash
python submission-tools/model_template.py YYYY-MM-DD team-model
Rscript submission-tools/model_template.R YYYY-MM-DD team-model
```

Skalet väljer automatiskt rätt fryst datafil för en retrospektiv omgång och
`target-data/time-series.csv` för en liveomgång. Data efter söndagen före
`reference_date` tas bort innan modellen körs. Därefter kontrollerar skalet
modellens resultat och skriver rätt kolumner, katalog och filnamn. Den
medföljande persistensmodellen är bara ett fungerande exempel och ska ersättas.

## Retrospektiva prognoser 2025/2026

Det finns 33 retrospektiva omgångar. Varje rad i
`retrospective-data/2025-2026/manifest.csv` anger söndagens `reference_date` och
vilken kapad datafil modellen ska använda. Alla tre platser och horisont 0–3 är
obligatoriska.

Deltagaren kan först samla samtliga 396 prognosrader i en CSV. R- och
Pythonverktygen delar sedan automatiskt filen i 33 korrekta prognosfiler. Alla
filer kan laddas upp tillsammans i en enda pull request.

Skapa först en tom batchmall med Python eller R:

```bash
python submission-tools/prepare_historical_submission.py template team-model
Rscript submission-tools/create_historical_submission.R team-model
```

Fyll i kolumnen `value` och validera och dela sedan batchen:

```bash
python submission-tools/prepare_historical_submission.py split historical-2025-2026-team-model.csv team-model
Rscript submission-tools/split_historical_submission.R historical-2025-2026-team-model.csv team-model
```

De 33 filerna skrivs till `model-output/team-model/`. Lägg även till modellens
metadatafil och ladda upp allt i samma pull request.
