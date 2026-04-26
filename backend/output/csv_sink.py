from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from domain.job import Job

log = logging.getLogger(__name__)


def save_csv(jobs: list[Job], output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"results_{timestamp}.csv"

    with open(out_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(Job.HEADERS)
        for job in jobs:
            writer.writerow(job.to_row())

    log.info("━━ CSV saved → %s  (%d rows)", out_path, len(jobs))
    return out_path
