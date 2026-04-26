from __future__ import annotations

from domain.job import Job


def deduplicate_jobs(jobs: list[Job]) -> tuple[list[Job], int]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique_jobs: list[Job] = []

    for job in jobs:
        key = (
            job.source,
            job.job_title,
            job.raw_facility,
            job.employment_type,
            job.salary_raw,
        )
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)

    removed_count = len(jobs) - len(unique_jobs)
    return unique_jobs, removed_count
