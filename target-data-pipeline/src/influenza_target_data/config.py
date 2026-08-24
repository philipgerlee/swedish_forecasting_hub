"""Stable source selections and output schema."""

API_URL = (
    "https://fohm-app.folkhalsomyndigheten.se/Folkhalsodata/api/v1/sv/"
    "A_Folkhalsodata/H_Sminet/Influensa/binflRegtid.px"
)

LOCATIONS = {
    "00": ("SE", "Sverige"),
    "12": ("SE-M", "Region Skåne"),
    "14": ("SE-O", "Västra Götalandsregionen"),
}

SOURCE_LABELS = {
    "00": "Riket",
    "12": "Skåne",
    "14": "Västra Götaland",
}

FIXED_SELECTIONS = {
    "Region": tuple(LOCATIONS),
    "Typ av influensa": ("1+2",),
    "Mått": ("1",),
    "Kön": ("1+2+0",),
}

TIME_DIMENSION = "År och vecka"

OUTPUT_COLUMNS = (
    "location",
    "location_name",
    "year",
    "week",
    "target_end_date",
    "value",
    "status",
    "release_status",
    "data_version",
    "source_region_code",
    "source_year_week",
    "official_release_time",
)

SEASON_START_WEEK = 40
SEASON_END_WEEK = 20
RISE_WARNING_FACTOR = 5
DECLINE_WARNING_FRACTION = 0.50
