args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: Rscript submission-tools/create_historical_submission.R team-model [output.csv] [manifest.csv]")
}

model_id <- args[[1]]
if (!grepl("^[A-Za-z0-9_+]+-[A-Za-z0-9_+]+$", model_id)) {
  stop("model_id must have the form team-model")
}
output <- if (length(args) >= 2) args[[2]] else paste0(
  "historical-2025-2026-", model_id, ".csv"
)
manifest_path <- if (length(args) >= 3) args[[3]] else file.path(
  "retrospective-data", "2025-2026", "manifest.csv"
)
manifest <- read.csv(manifest_path, stringsAsFactors = FALSE)
if (nrow(manifest) != 33 || length(unique(manifest$reference_date)) != 33) {
  stop("manifest must contain 33 unique reference dates")
}

submission <- do.call(rbind, lapply(manifest$reference_date, function(reference_date) {
  grid <- expand.grid(
    horizon = 0:3,
    location = c("SE", "SE-M", "SE-O"),
    KEEP.OUT.ATTRS = FALSE,
    stringsAsFactors = FALSE
  )
  grid$reference_date <- reference_date
  grid$target <- "weekly incident influenza cases"
  grid$output_type <- "mean"
  grid$output_type_id <- NA_character_
  grid$value <- NA_real_
  grid[c(
    "reference_date", "target", "horizon", "location",
    "output_type", "output_type_id", "value"
  )]
}))
write.csv(submission, output, row.names = FALSE, na = "")
message("Wrote ", nrow(submission), " rows to ", output)
