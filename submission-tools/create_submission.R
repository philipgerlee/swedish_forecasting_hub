args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript submission-tools/create_submission.R YYYY-MM-DD team-model [output.csv]")
}

reference_date <- as.Date(args[[1]])
if (is.na(reference_date) || as.POSIXlt(reference_date)$wday != 0) {
  stop("reference_date must be a Sunday in YYYY-MM-DD format")
}
model_id <- args[[2]]
output <- if (length(args) >= 3) args[[3]] else file.path(
  "model-output", model_id, paste0(reference_date, "-", model_id, ".csv")
)
dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)

submission <- expand.grid(
  horizon = 0:3,
  location = c("SE", "SE-M", "SE-O"),
  KEEP.OUT.ATTRS = FALSE,
  stringsAsFactors = FALSE
)
submission$reference_date <- as.character(reference_date)
submission$target <- "weekly incident influenza cases"
submission$output_type <- "mean"
submission$output_type_id <- NA_character_
submission$value <- NA_real_
submission <- submission[c(
  "reference_date", "target", "horizon", "location",
  "output_type", "output_type_id", "value"
)]
write.csv(submission, output, row.names = FALSE, na = "")
message(output)
