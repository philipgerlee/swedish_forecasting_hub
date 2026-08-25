# Starter program: replace only the body of forecast_model with your model.
# Run from the repository root:
#
#   Rscript submission-tools/model_template.R YYYY-MM-DD team-model
#   Rscript submission-tools/model_template.R --all-historical team-model
#
# Add an optional input CSV and output CSV as the third and fourth arguments.

locations <- c("SE", "SE-M", "SE-O")
horizons <- 0:3
target_name <- "weekly incident influenza cases"

# ---------------------------------------------------------------------------
# REPLACE THIS FUNCTION BODY WITH YOUR MODEL
# ---------------------------------------------------------------------------
forecast_model <- function(data, reference_date) {
  # data has already been cut at reference_date minus seven days.
  # This example is a persistence model that repeats the latest observation.
  output <- do.call(rbind, lapply(locations, function(location) {
    observed <- data[
      data$location == location &
        data$status == "available" &
        !is.na(data$value),
      ,
      drop = FALSE
    ]
    if (nrow(observed) == 0) {
      stop("No available observations for ", location)
    }
    latest <- observed[which.max(as.Date(observed$target_end_date)), ]
    data.frame(
      location = location,
      horizon = horizons,
      value = rep(as.numeric(latest$value), length(horizons)),
      stringsAsFactors = FALSE
    )
  }))
  output
}

# ---------------------------------------------------------------------------
# HUB FILE HANDLING — NORMALLY NO CHANGES ARE NEEDED BELOW THIS LINE
# ---------------------------------------------------------------------------
default_input_path <- function(reference_date) {
  retrospective <- file.path(
    "retrospective-data", "2025-2026", "rounds",
    paste0(reference_date, ".csv")
  )
  if (file.exists(retrospective)) {
    retrospective
  } else {
    file.path("target-data", "time-series.csv")
  }
}

prepare_round <- function(reference_date, model_id, input_path, output_path) {
  data <- read.csv(
    input_path,
    stringsAsFactors = FALSE,
    check.names = FALSE,
    na.strings = c("", "NA", "N/A")
  )
  required_input <- c("location", "target_end_date", "value", "status")
  missing_input <- setdiff(required_input, names(data))
  if (length(missing_input) > 0) {
    stop("Input data is missing columns: ", paste(missing_input, collapse = ", "))
  }
  target_dates <- as.Date(data$target_end_date)
  if (any(is.na(target_dates))) {
    stop("Input data contains an invalid target_end_date")
  }
  cutoff <- reference_date - 7
  data <- data[target_dates <= cutoff, , drop = FALSE]
  if (nrow(data) == 0) {
    stop("No input observations are available through ", cutoff)
  }

  forecasts <- forecast_model(data, reference_date)
  required_forecast <- c("location", "horizon", "value")
  if (!is.data.frame(forecasts) || !all(required_forecast %in% names(forecasts))) {
    stop("forecast_model must return a data frame with location, horizon and value")
  }
  if (nrow(forecasts) == 0) {
    stop("forecast_model returned no forecasts")
  }
  if (any(!forecasts$location %in% locations)) {
    stop("forecast_model returned an unsupported location")
  }
  forecast_horizons <- suppressWarnings(as.integer(forecasts$horizon))
  forecast_values <- suppressWarnings(as.numeric(forecasts$value))
  if (any(is.na(forecast_horizons)) || any(!forecast_horizons %in% horizons)) {
    stop("forecast_model returned an unsupported horizon")
  }
  if (any(is.na(forecast_values)) || any(!is.finite(forecast_values)) || any(forecast_values < 0)) {
    stop("Forecast values must be finite and at least zero")
  }
  keys <- paste(forecasts$location, forecast_horizons, sep = ":")
  if (anyDuplicated(keys)) {
    stop("forecast_model returned a duplicate location and horizon")
  }
  for (location in unique(forecasts$location)) {
    found <- sort(forecast_horizons[forecasts$location == location])
    if (!identical(found, horizons)) {
      stop("Every submitted location needs horizons 0-3")
    }
  }
  historical_start <- as.Date("2025-10-05")
  historical_end <- as.Date("2026-05-17")
  if (
    reference_date >= historical_start &&
      reference_date <= historical_end &&
      !setequal(unique(forecasts$location), locations)
  ) {
    stop("Historical rounds require forecasts for all locations")
  }

  submission <- data.frame(
    reference_date = rep(as.character(reference_date), nrow(forecasts)),
    target = rep(target_name, nrow(forecasts)),
    horizon = forecast_horizons,
    location = forecasts$location,
    output_type = rep("mean", nrow(forecasts)),
    output_type_id = rep(NA_character_, nrow(forecasts)),
    value = forecast_values,
    stringsAsFactors = FALSE
  )
  submission$location <- factor(submission$location, levels = locations)
  submission <- submission[order(submission$location, submission$horizon), ]
  submission$location <- as.character(submission$location)
  list(
    reference_date = reference_date,
    input_path = input_path,
    output_path = output_path,
    submission = submission
  )
}

write_round <- function(prepared) {
  dir.create(dirname(prepared$output_path), recursive = TRUE, showWarnings = FALSE)
  write.csv(prepared$submission, prepared$output_path, row.names = FALSE, na = "")
  message("Read ", prepared$input_path)
  message("Wrote ", prepared$output_path)
}

args <- commandArgs(trailingOnly = TRUE)
usage <- paste(
  "Usage:",
  "Rscript submission-tools/model_template.R YYYY-MM-DD team-model [input.csv] [output.csv]",
  "or Rscript submission-tools/model_template.R --all-historical team-model [output-root]",
  sep = "\n  "
)
if (length(args) < 2) {
  stop(usage)
}

all_historical <- identical(args[[1]], "--all-historical")
model_id <- args[[2]]
if (!grepl("^[A-Za-z0-9_+]+-[A-Za-z0-9_+]+$", model_id)) {
  stop("model_id must have the form team-model")
}

if (all_historical) {
  if (length(args) > 3) {
    stop(usage)
  }
  output_root <- if (length(args) == 3) args[[3]] else "model-output"
  manifest_path <- file.path("retrospective-data", "2025-2026", "manifest.csv")
  manifest <- read.csv(manifest_path, stringsAsFactors = FALSE)
  reference_dates <- as.Date(manifest$reference_date)
  if (
    length(reference_dates) != 33 ||
      length(unique(reference_dates)) != 33 ||
      any(is.na(reference_dates)) ||
      !identical(reference_dates, sort(reference_dates)) ||
      any(as.POSIXlt(reference_dates)$wday != 0)
  ) {
    stop("Historical manifest must contain 33 unique ordered Sundays")
  }
  prepared <- lapply(reference_dates, function(reference_date) {
    input_path <- default_input_path(reference_date)
    output_path <- file.path(
      output_root, model_id, paste0(reference_date, "-", model_id, ".csv")
    )
    prepare_round(reference_date, model_id, input_path, output_path)
  })
  invisible(lapply(prepared, write_round))
  message("Wrote ", length(prepared), " historical forecast files")
} else {
  reference_date <- as.Date(args[[1]])
  if (is.na(reference_date) || as.POSIXlt(reference_date)$wday != 0) {
    stop("reference_date must be a Sunday in YYYY-MM-DD format")
  }
  input_path <- if (length(args) >= 3) args[[3]] else default_input_path(reference_date)
  output_path <- if (length(args) >= 4) args[[4]] else file.path(
    "model-output", model_id, paste0(reference_date, "-", model_id, ".csv")
  )
  if (length(args) > 4) {
    stop(usage)
  }
  write_round(prepare_round(reference_date, model_id, input_path, output_path))
}
