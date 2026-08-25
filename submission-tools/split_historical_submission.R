args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript submission-tools/split_historical_submission.R batch.csv team-model [output-root] [manifest.csv]")
}

batch_path <- args[[1]]
model_id <- args[[2]]
output_root <- if (length(args) >= 3) args[[3]] else "model-output"
manifest_path <- if (length(args) >= 4) args[[4]] else file.path(
  "retrospective-data", "2025-2026", "manifest.csv"
)
if (!grepl("^[A-Za-z0-9_+]+-[A-Za-z0-9_+]+$", model_id)) {
  stop("model_id must have the form team-model")
}
expected_columns <- c(
  "reference_date", "target", "horizon", "location",
  "output_type", "output_type_id", "value"
)
manifest <- read.csv(manifest_path, stringsAsFactors = FALSE)
expected_dates <- manifest$reference_date
if (length(expected_dates) != 33 || length(unique(expected_dates)) != 33) {
  stop("manifest must contain 33 unique reference dates")
}
batch <- read.csv(
  batch_path,
  stringsAsFactors = FALSE,
  check.names = FALSE,
  na.strings = c("", "NA", "N/A")
)
if (!identical(names(batch), expected_columns)) {
  stop("columns are missing, extra, or in the wrong order")
}
if (!setequal(unique(batch$reference_date), expected_dates)) {
  stop("batch reference dates do not match the manifest")
}

temporary_root <- tempfile("historical-submission-")
temporary_model <- file.path(temporary_root, model_id)
dir.create(temporary_model, recursive = TRUE)
for (reference_date in expected_dates) {
  rows <- batch[batch$reference_date == reference_date, , drop = FALSE]
  if (nrow(rows) != 12) {
    stop("each reference_date must contain exactly 12 rows")
  }
  for (location in c("SE", "SE-M", "SE-O")) {
    location_rows <- rows[rows$location == location, , drop = FALSE]
    if (nrow(location_rows) != 4 || !identical(sort(as.integer(location_rows$horizon)), 0:3)) {
      stop(paste(reference_date, location, "must contain horizons 0-3 exactly once"))
    }
  }
  if (any(rows$target != "weekly incident influenza cases")) {
    stop(paste(reference_date, "contains an invalid target"))
  }
  if (any(rows$output_type != "mean") || any(!is.na(rows$output_type_id))) {
    stop(paste(reference_date, "contains an invalid output type"))
  }
  values <- suppressWarnings(as.numeric(rows$value))
  if (any(is.na(values)) || any(!is.finite(values)) || any(values < 0)) {
    stop(paste(reference_date, "contains an invalid value"))
  }
  path <- file.path(temporary_model, paste0(reference_date, "-", model_id, ".csv"))
  write.csv(rows, path, row.names = FALSE, na = "")
}

destination <- file.path(output_root, model_id)
dir.create(destination, recursive = TRUE, showWarnings = FALSE)
files <- list.files(temporary_model, full.names = TRUE)
if (!all(file.copy(files, destination, overwrite = TRUE))) {
  stop("could not copy all validated forecast files")
}
unlink(temporary_root, recursive = TRUE)
message("Validated and wrote ", length(files), " forecast files to ", destination)
