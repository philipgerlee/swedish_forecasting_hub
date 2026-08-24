args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: Rscript submission-tools/validate_submission.R path/to/submission.csv")
}

path <- args[[1]]
expected_columns <- c(
  "reference_date", "target", "horizon", "location",
  "output_type", "output_type_id", "value"
)
allowed_locations <- c("SE", "SE-M", "SE-O")
allowed_horizons <- 0:3
target_name <- "weekly incident influenza cases"

fail <- function(message) {
  message("ERROR: ", message)
  quit(status = 1)
}

filename <- basename(path)
match <- regexec(
  "^(\\d{4}-\\d{2}-\\d{2})-([A-Za-z0-9_+]+-[A-Za-z0-9_+]+)\\.csv$",
  filename
)
parts <- regmatches(filename, match)[[1]]
if (length(parts) == 0) {
  fail("filename must be YYYY-MM-DD-<team>-<model>.csv")
}
reference_date <- parts[[2]]
model_id <- parts[[3]]
if (basename(dirname(path)) != model_id) {
  fail("parent directory must equal model_id")
}
parsed_date <- as.Date(reference_date)
if (is.na(parsed_date) || as.POSIXlt(parsed_date)$wday != 0) {
  fail("reference_date must be a valid Sunday")
}

submission <- tryCatch(
  read.csv(
    path,
    stringsAsFactors = FALSE,
    check.names = FALSE,
    na.strings = c("", "NA", "N/A")
  ),
  error = function(error) fail(conditionMessage(error))
)
if (!identical(names(submission), expected_columns)) {
  fail("columns are missing, extra, or in the wrong order")
}
if (nrow(submission) == 0) {
  fail("submission contains no rows")
}

accepted <- character()
rejected <- character()
for (location in unique(submission$location)) {
  errors <- character()
  if (is.na(location) || !(location %in% allowed_locations)) {
    errors <- c(errors, "unsupported location")
  }
  rows <- submission[submission$location == location, , drop = FALSE]
  if (any(rows$reference_date != reference_date, na.rm = TRUE) || any(is.na(rows$reference_date))) {
    errors <- c(errors, "reference_date does not match filename")
  }
  if (any(rows$target != target_name, na.rm = TRUE) || any(is.na(rows$target))) {
    errors <- c(errors, "invalid target")
  }
  if (any(rows$output_type != "mean", na.rm = TRUE) || any(is.na(rows$output_type))) {
    errors <- c(errors, "output_type must be mean")
  }
  if (any(!is.na(rows$output_type_id))) {
    errors <- c(errors, "output_type_id must be empty or NA")
  }
  horizons <- suppressWarnings(as.integer(rows$horizon))
  if (any(is.na(horizons)) || !identical(sort(horizons), allowed_horizons)) {
    errors <- c(errors, "horizons 0-3 are required exactly once")
  }
  values <- suppressWarnings(as.numeric(rows$value))
  if (any(is.na(values)) || any(!is.finite(values)) || any(values < 0)) {
    errors <- c(errors, "values must be numeric, finite and at least zero")
  }
  if (any(values > 100000, na.rm = TRUE)) {
    message("WARNING: high value requires manual review (", location, ")")
  }
  if (length(errors) == 0) {
    accepted <- c(accepted, location)
  } else {
    rejected <- c(rejected, ifelse(is.na(location), "<empty>", location))
    for (error in unique(errors)) {
      message("ERROR [", location, "]: ", error)
    }
  }
}

if (length(accepted) == 0) {
  fail("no valid location remains")
}
message("Accepted locations: ", paste(sort(accepted), collapse = ", "))
if (length(rejected) > 0) {
  message("Rejected locations: ", paste(sort(rejected), collapse = ", "))
  message("PARTIAL")
} else {
  message("PASS")
}
