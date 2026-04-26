from __future__ import annotations

import re
from datetime import datetime, timedelta

from dateutil import parser as dateutil_parser

from domain.job import Job

_REIWA_OFFSET = 2018


def _normalize_japanese_date(raw: str) -> str:
    value = raw.strip()

    match = re.search(r"令和\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", value)
    if match:
        year = _REIWA_OFFSET + int(match.group(1))
        return f"{year}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"

    match = re.search(r"平成\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", value)
    if match:
        year = 1988 + int(match.group(1))
        return f"{year}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"

    match = re.search(r"(\d{4})\s*年\s*(\d+)\s*月\s*(\d+)\s*日", value)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"

    match = re.search(r"(\d+)\s*月\s*(\d+)\s*日", value)
    if match:
        return f"{datetime.now().year}-{match.group(1).zfill(2)}-{match.group(2).zfill(2)}"

    return value


def is_within_deadline(job: Job) -> bool:
    raw = (job.application_deadline or "").strip()
    if not raw:
        return True

    try:
        normalized = _normalize_japanese_date(raw)
        deadline = dateutil_parser.parse(normalized, dayfirst=False).date()
    except Exception:
        return True

    today = datetime.now().date()
    return deadline >= (today - timedelta(days=30))
