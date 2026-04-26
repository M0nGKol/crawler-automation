from __future__ import annotations

import json
import logging
import re
from typing import Any

from domain.job import Job

log = logging.getLogger(__name__)


def _simple_mask(name: str) -> str:
    if not name:
        return ""
    keep = min(3, len(name))
    return name[:keep] + "●" * max(0, len(name) - keep)


def _simple_salary_mask(salary_str: str) -> str:
    if not salary_str:
        return ""

    match = re.search(r"(\d+)\s*万\s*円", salary_str)
    if match:
        value = int(match.group(1))
        lo = (value // 10) * 10
        hi = lo + 10
        return f"{lo}〜{hi}万円"

    match = re.search(r"([\d,]+)\s*円", salary_str)
    if match:
        value = int(match.group(1).replace(",", ""))
        if value >= 100_000:
            lo = (value // 10_000) * 10_000
            hi = lo + 10_000
            return f"{lo:,}〜{hi:,}円"
        if value >= 1_000:
            lo = (value // 500) * 500
            hi = lo + 500
            return f"{lo:,}〜{hi:,}円"

    return "非公開"


def mask_jobs(jobs: list[Job], claude: Any, masking_limit: int) -> list[Job]:
    if not jobs:
        return jobs

    to_mask = jobs[:masking_limit]
    rest = jobs[masking_limit:]

    if not claude:
        log.warning("No ANTHROPIC_API_KEY — using rule-based masking")
        for job in jobs:
            job.masked_facility = _simple_mask(job.raw_facility)
            job.salary_masked = _simple_salary_mask(job.salary_raw)
        return jobs

    log.info("━━ Masking %d listings via Claude …", len(to_mask))
    batch_size = 20

    for i in range(0, len(to_mask), batch_size):
        batch = to_mask[i : i + batch_size]
        payload = [{"id": j.id, "facility": j.raw_facility, "salary": j.salary_raw} for j in batch]

        try:
            resp = claude.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1500,
                system="""You mask Japanese healthcare job listing data for privacy.
For each item return JSON with:
  id           — same as input, unchanged
  masked_facility — partial redact: keep first 3–4 kanji + ●● suffix
                    e.g. "東京大学医学部附属病院" → "東京大学●●●●"
                    e.g. "慶應義塾大学病院" → "慶應義●●●"
                    if null or empty, return ""
  salary_masked — round to nearest 10万円 bracket, e.g. "月給45万円" → "40〜50万円"
                  if null or empty, return ""
Return ONLY a JSON array. No markdown. No explanation.""",
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )

            raw = resp.content[0].text.strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            masked_list = json.loads(raw)

            mask_map = {m["id"]: m for m in masked_list}
            for job in batch:
                masked = mask_map.get(job.id, {})
                job.masked_facility = masked.get("masked_facility", _simple_mask(job.raw_facility))
                job.salary_masked = masked.get("salary_masked", "")

            log.info("  Batch %d–%d masked ✓", i + 1, i + len(batch))
        except Exception as exc:
            log.error("  Masking batch failed: %s — using rule-based fallback", exc)
            for job in batch:
                job.masked_facility = _simple_mask(job.raw_facility)
                job.salary_masked = _simple_salary_mask(job.salary_raw)

    for job in rest:
        job.masked_facility = _simple_mask(job.raw_facility)
        job.salary_masked = _simple_salary_mask(job.salary_raw)

    return jobs
