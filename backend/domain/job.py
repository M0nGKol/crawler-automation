from __future__ import annotations

import uuid
from datetime import datetime


class Job:
    HEADERS = [
        "id",
        "source",
        "raw_facility",
        "masked_facility",
        "job_title",
        "location",
        "job_description",
        "requirements",
        "salary_raw",
        "salary_masked",
        "employment_type",
        "application_deadline",
        "contact_information",
        "url",
        "scraped_at",
    ]

    def __init__(self, source: str, mode: str, **kw: str) -> None:
        self.id = uuid.uuid4().hex[:10]
        self.source = source
        self.mode = mode
        self.raw_facility = kw.get("facility_name") or kw.get("raw_facility", "")
        self.masked_facility = ""
        self.job_title = kw.get("job_title", "")
        self.location = kw.get("location", "")
        self.job_description = kw.get("job_description", "")
        self.requirements = kw.get("requirements", "")
        self.salary_raw = kw.get("salary_raw", "")
        self.salary_masked = ""
        self.employment_type = kw.get("employment_type", "")
        self.application_deadline = kw.get("application_deadline", "")
        self.contact_information = kw.get("contact_information", "")
        self.url = kw.get("url", "")
        self.scraped_at = datetime.now().isoformat(timespec="seconds")

    def to_row(self) -> list[str]:
        return [
            self.id,
            self.source,
            self.raw_facility,
            self.masked_facility,
            self.job_title,
            self.location,
            self.job_description,
            self.requirements,
            self.salary_raw,
            self.salary_masked,
            self.employment_type,
            self.application_deadline,
            self.contact_information,
            self.url,
            self.scraped_at,
        ]
