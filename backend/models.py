"""
Output-only dataclasses for raw and masked job data.

Both share the same 13-field schema so they can be written to
Google Sheets / CSV with identical column headers while keeping
raw vs. masked data strictly separated.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Canonical column order used in every output sink
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
    "scraped_at",
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
    scraped_at: str = ""

    def to_row(self) -> list[str]:
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
            self.scraped_at,
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
    scraped_at: str = ""

    def to_row(self) -> list[str]:
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
            self.scraped_at,
        ]
