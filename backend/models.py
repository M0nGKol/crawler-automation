"""
Output-only dataclasses for raw and masked job data.

Both share the same schema so they can be written to Google Sheets / CSV
with correct column headers while keeping raw vs. masked data strictly
separated.

Note: scraped_at and pipeline_stage are kept as dataclass fields so the
pipeline can still access them internally, but they are NOT included in
to_row() / header lists — they are not shown to end users in sheets or CSV.
"""
from __future__ import annotations

from dataclasses import dataclass

# Generic column order — kept for backward-compat with any legacy callers.
# New code should use RAW_JOB_HEADERS / MASKED_JOB_HEADERS instead.
JOB_HEADERS = [
    "id",
    "source",
    "facility",
    "job_title",
    "location",
    "job_description",
    "requirements",
    "salary",
    "employment_type",
    "application_deadline",
    "contact_information",
    "url",
]

# Explicit per-tab headers for Google Sheets / CSV.
# Uses tab-specific names so raw vs. masked columns are unambiguous.
# scraped_at and pipeline_stage are intentionally excluded — internal use only.
RAW_JOB_HEADERS = [
    "id",
    "source",
    "raw_facility",
    "job_title",
    "location",
    "job_description",
    "requirements",
    "salary_raw",
    "employment_type",
    "application_deadline",
    "contact_information",
    "url",
]

MASKED_JOB_HEADERS = [
    "id",
    "source",
    "masked_facility",
    "job_title",
    "location",
    "job_description",
    "requirements",
    "salary_masked",
    "employment_type",
    "application_deadline",
    "contact_information",
    "url",
]


@dataclass
class JobRaw:
    """Holds the un-redacted job data for the raw_data output tab/file."""

    id: str = ""
    source: str = ""
    facility: str = ""          # raw facility name
    job_title: str = ""
    location: str = ""
    job_description: str = ""
    requirements: str = ""
    salary: str = ""            # raw salary string
    employment_type: str = ""
    application_deadline: str = ""
    contact_information: str = ""
    url: str = ""
    # Internal fields — not written to sheets/CSV output
    scraped_at: str = ""
    pipeline_stage: str = ""

    def to_row(self) -> list[str]:
        """Returns only the user-facing columns (excludes scraped_at, pipeline_stage)."""
        return [
            self.id,
            self.source,
            self.facility,
            self.job_title,
            self.location,
            self.job_description,
            self.requirements,
            self.salary,
            self.employment_type,
            self.application_deadline,
            self.contact_information,
            self.url,
        ]


@dataclass
class JobMasked:
    """Holds the privacy-redacted job data for the masked_data output tab/file."""

    id: str = ""
    source: str = ""
    facility: str = "●●●"       # masked facility name
    job_title: str = ""
    location: str = ""
    job_description: str = ""
    requirements: str = ""
    salary: str = "●●●"         # masked salary
    employment_type: str = ""
    application_deadline: str = ""
    contact_information: str = ""
    url: str = ""
    # Internal fields — not written to sheets/CSV output
    scraped_at: str = ""
    pipeline_stage: str = ""

    def to_row(self) -> list[str]:
        """Returns only the user-facing columns (excludes scraped_at, pipeline_stage)."""
        return [
            self.id,
            self.source,
            self.facility,
            self.job_title,
            self.location,
            self.job_description,
            self.requirements,
            self.salary,
            self.employment_type,
            self.application_deadline,
            self.contact_information,
            self.url,
        ]
