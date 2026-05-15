"""
CSV output sink.

Writes two fixed-name files:
  output/raw_data.csv    — raw facility + raw salary + pipeline_stage
  output/masked_data.csv — masked facility + masked salary + pipeline_stage

Each file uses its own header list (RAW_JOB_HEADERS / MASKED_JOB_HEADERS)
so column names are unambiguous when the client opens both files in Excel.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from models import MASKED_JOB_HEADERS, RAW_JOB_HEADERS, JobMasked, JobRaw

log = logging.getLogger(__name__)


def save_csv(
    jobs_raw: list[JobRaw],
    jobs_masked: list[JobMasked],
    output_dir: str = "output",
) -> tuple[Path, Path]:
    """
    Write raw_data.csv and masked_data.csv to output_dir.

    raw_data.csv    uses RAW_JOB_HEADERS  (raw_facility, salary_raw, …)
    masked_data.csv uses MASKED_JOB_HEADERS (masked_facility, salary_masked, …)

    Returns (raw_path, masked_path).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    raw_path = out / "raw_data.csv"
    masked_path = out / "masked_data.csv"

    # ── raw_data.csv ──────────────────────────────────────────────────────────
    with open(raw_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(RAW_JOB_HEADERS)       # raw_facility, salary_raw, pipeline_stage
        for job in jobs_raw:
            writer.writerow(job.to_row())
    log.info("━━ CSV saved → %s  (%d rows, %d cols)", raw_path, len(jobs_raw), len(RAW_JOB_HEADERS))

    # ── masked_data.csv ───────────────────────────────────────────────────────
    with open(masked_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(MASKED_JOB_HEADERS)    # masked_facility, salary_masked, pipeline_stage
        for job in jobs_masked:
            writer.writerow(job.to_row())
    log.info("━━ CSV saved → %s  (%d rows, %d cols)", masked_path, len(jobs_masked), len(MASKED_JOB_HEADERS))

    return raw_path, masked_path
