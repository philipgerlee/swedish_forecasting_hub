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
