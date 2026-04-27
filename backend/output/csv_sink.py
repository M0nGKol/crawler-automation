"""
CSV output sink.

Writes two fixed-name files:
  output/raw_data.csv    — raw facility + raw salary
  output/masked_data.csv — masked facility + masked salary

Both share the same 13-column schema defined in models.JOB_HEADERS.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from models import JOB_HEADERS, JobMasked, JobRaw

log = logging.getLogger(__name__)


def save_csv(
    jobs_raw: list[JobRaw],
    jobs_masked: list[JobMasked],
    output_dir: str = "output",
) -> tuple[Path, Path]:
    """
    Write raw_data.csv and masked_data.csv to output_dir.

    Returns (raw_path, masked_path).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    raw_path = out / "raw_data.csv"
    masked_path = out / "masked_data.csv"

    # ── raw_data.csv ──────────────────────────────────────────────────────
    with open(raw_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(JOB_HEADERS)
        for job in jobs_raw:
            writer.writerow(job.to_row())
    log.info("━━ CSV saved → %s  (%d rows)", raw_path, len(jobs_raw))

    # ── masked_data.csv ───────────────────────────────────────────────────
    with open(masked_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(JOB_HEADERS)
        for job in jobs_masked:
            writer.writerow(job.to_row())
    log.info("━━ CSV saved → %s  (%d rows)", masked_path, len(jobs_masked))

    return raw_path, masked_path
