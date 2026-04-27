"""
Content-based deduplication using MD5 hashes.

Deduplicates within the current run (in-memory set) AND across
previous runs by checking the job_hashes SQLite table.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from database import JobHash, SessionLocal

log = logging.getLogger(__name__)


def _compute_hash(job: dict[str, Any]) -> str:
    """MD5 hash of source|job_title|facility|location."""
    key = (
        f"{job.get('source', '')}|"
        f"{job.get('job_title', '')}|"
        f"{job.get('facility', job.get('raw_facility', ''))}|"
        f"{job.get('location', '')}"
    )
    return hashlib.md5(key.encode()).hexdigest()


def deduplicate_jobs(
    jobs: list[Any],  # list[Job] — kept as Any to avoid circular import
) -> tuple[list[Any], int]:
    """
    Remove duplicate jobs using MD5 content hashing.

    1. Computes a hash per job.
    2. Skips hashes already seen in this run (in-memory).
    3. Skips hashes already stored in the job_hashes DB table.
    4. Persists new hashes to DB so future runs skip them too.

    Returns (unique_jobs, removed_count).
    """
    if not jobs:
        return [], 0

    db = SessionLocal()
    try:
        # Build set of already-known hashes from the DB
        existing_hashes: set[str] = {
            row.hash for row in db.query(JobHash.hash).all()
        }
    finally:
        db.close()

    seen_this_run: set[str] = set()
    unique_jobs: list[Any] = []
    new_hashes: list[JobHash] = []

    for job in jobs:
        # Build a dict-like view of the job regardless of type
        if hasattr(job, "__dict__"):
            job_dict = job.__dict__
        else:
            job_dict = dict(job)

        job_hash = _compute_hash(job_dict)

        if job_hash in seen_this_run or job_hash in existing_hashes:
            continue

        seen_this_run.add(job_hash)
        existing_hashes.add(job_hash)
        unique_jobs.append(job)
        new_hashes.append(
            JobHash(
                hash=job_hash,
                source=str(job_dict.get("source", "")),
            )
        )

    # Persist new hashes to DB
    if new_hashes:
        db = SessionLocal()
        try:
            db.bulk_save_objects(new_hashes)
            db.commit()
        except Exception as exc:
            log.error("Failed to persist job hashes: %s", exc)
            db.rollback()
        finally:
            db.close()

    removed = len(jobs) - len(unique_jobs)
    log.info("Deduplication: kept %d / %d jobs (%d removed)", len(unique_jobs), len(jobs), removed)
    return unique_jobs, removed
