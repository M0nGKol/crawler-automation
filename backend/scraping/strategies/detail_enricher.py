"""
Detail-page enrichment for non-Indeed sites (Job Medley, Osaka University, etc).

After a listing scrape produces a Job with a URL, this module fetches the
detail page and uses Claude Haiku to fill in fields that the listing card
didn't have (requirements, application_deadline, contact_information,
full job_description, full salary, etc).

Cost controls:
  - DETAIL_ENRICH_ENABLED (default: true)
  - DETAIL_ENRICH_MAX_PER_SITE (default: 10) — hard cap per site per run
  - Skips jobs that already have all critical fields populated
  - Skips when no URL is set on the Job
  - Respects should_stop() between fetches
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

import httpx

from domain.job import Job

log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
ENABLED: bool = os.getenv("DETAIL_ENRICH_ENABLED", "true").lower() in ("1", "true", "yes")
MAX_PER_SITE: int = int(os.getenv("DETAIL_ENRICH_MAX_PER_SITE", "10"))
FETCH_TIMEOUT_SECONDS: int = int(os.getenv("DETAIL_ENRICH_TIMEOUT", "30"))

# Fields we consider "critical" — a job is considered enriched once these are filled.
CRITICAL_FIELDS = (
    "job_description",
    "requirements",
    "salary_raw",
    "employment_type",
    "application_deadline",
    "contact_information",
)

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _needs_enrichment(job: Job) -> bool:
    """A job needs enrichment if any critical field is empty."""
    return any(not (getattr(job, f, "") or "").strip() for f in CRITICAL_FIELDS)


async def _fetch_detail_html(url: str) -> str | None:
    """Fetch the detail page HTML. Returns None on network failure."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(float(FETCH_TIMEOUT_SECONDS)),
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            http2=True,
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                log.warning("[ENRICH] Non-200 (%d) for %s", response.status_code, url[:80])
                return None
            return response.text
    except Exception as exc:
        log.warning("[ENRICH] Fetch failed for %s: %s", url[:80], exc)
        return None


def _trim_html(html: str, max_chars: int = 20_000) -> str:
    """Strip noise from HTML before sending to Claude."""
    body = html
    for tag in ("script", "style", "nav", "footer", "header", "head"):
        body = re.sub(rf"<{tag}[\s>].*?</{tag}>", "", body, flags=re.DOTALL | re.IGNORECASE)
    # Prefer <main>, <article>, or a content div when one is present
    for pattern in (
        r"<main[\s>].*?</main>",
        r"<article[\s>].*?</article>",
        r'<div[^>]+(?:id|class)=["\'][^"\']*(?:content|detail|job)[^"\']*["\'][^>]*>.*?</div>',
    ):
        match = re.search(pattern, body, re.DOTALL | re.IGNORECASE)
        if match and len(match.group(0)) > 500:
            return match.group(0)[:max_chars]
    return body[:max_chars]


def _extract_with_claude(html: str, job: Job, claude: Any) -> dict[str, str]:
    """Ask Claude Haiku to pull missing fields out of a detail page."""
    body = _trim_html(html)
    missing = [f for f in CRITICAL_FIELDS if not (getattr(job, f, "") or "").strip()]

    try:
        response = claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            system=(
                "You extract structured data from Japanese healthcare job detail pages. "
                "Return ONLY a JSON object — no markdown fences, no commentary. "
                "Use the exact field names below. Use empty string for any field you cannot find. "
                "Quote text verbatim from the page when possible (do NOT summarize).\n\n"
                "Fields:\n"
                '  "job_title": position name (職種, ポジション名)\n'
                '  "facility_name": hospital / clinic / facility name (施設名, 事業所名)\n'
                '  "location": full address or work location (勤務地, 所在地)\n'
                '  "job_description": role description verbatim (仕事内容, 業務内容)\n'
                '  "requirements": qualifications needed (応募資格, 必要資格, 応募条件)\n'
                '  "salary_raw": salary text verbatim (給与, 月給, 年収, 時給)\n'
                '  "employment_type": 正社員 / パート / 契約社員 / 派遣 etc (雇用形態)\n'
                '  "application_deadline": deadline (応募期限, 募集期限, 締切)\n'
                '  "contact_information": phone, email, or contact name (連絡先, 採用担当)\n'
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"URL: {job.url}\n"
                    f"Fields currently missing on this job: {', '.join(missing) or '(none — verify)'}\n\n"
                    f"HTML:\n{body}"
                ),
            }],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, dict):
            log.warning("[ENRICH] Claude returned non-dict for %s", job.url[:60])
            return {}
        return {k: str(v or "") for k, v in data.items()}
    except json.JSONDecodeError as exc:
        log.warning("[ENRICH] JSON parse failed for %s: %s", job.url[:60], exc)
        return {}
    except Exception as exc:
        log.warning("[ENRICH] Claude extraction failed for %s: %s", job.url[:60], exc)
        return {}


def _fill_empty(job: Job, extracted: dict[str, str]) -> list[str]:
    """Copy extracted values into the Job, but only into fields that are empty.
    Returns the list of field names that were filled."""
    filled: list[str] = []
    for field, value in extracted.items():
        if not value or not value.strip():
            continue
        current = getattr(job, field, None)
        # job_title and facility_name use slightly different attribute names —
        # only update if the attribute genuinely exists and is empty
        if hasattr(job, field) and not (current or "").strip():
            setattr(job, field, value.strip())
            filled.append(field)
    return filled


async def enrich_jobs_with_detail_pages(
    jobs: list[Job],
    site_name: str,
    claude: Any,
    should_stop: Callable[[], bool] | None = None,
) -> list[Job]:
    """
    Visit each job's detail URL and fill in fields that the listing card missed.

    Mutates the Job objects in-place and also returns the same list for chaining.
    Capped at MAX_PER_SITE fetches per site to keep cost predictable.
    """
    if not ENABLED:
        log.info("[ENRICH] %s: disabled (DETAIL_ENRICH_ENABLED=false)", site_name)
        return jobs
    if not claude:
        log.info("[ENRICH] %s: skipped (no Claude client available)", site_name)
        return jobs
    if not jobs:
        return jobs

    needs = [j for j in jobs if j.url and _needs_enrichment(j)]
    to_fetch = needs[:MAX_PER_SITE]
    capped = len(needs) - len(to_fetch)
    complete = len(jobs) - len(needs)

    log.info(
        "[ENRICH] %s: %d detail fetches (+%d already complete, +%d skipped by cap)",
        site_name,
        len(to_fetch),
        complete,
        capped,
    )

    for idx, job in enumerate(to_fetch, start=1):
        if should_stop and should_stop():
            log.info("[ENRICH] %s: stopped by user after %d/%d", site_name, idx - 1, len(to_fetch))
            break

        html = await _fetch_detail_html(job.url)
        if not html or len(html) < 500:
            log.warning("[ENRICH] %s: empty/short HTML for %s", site_name, job.url[:60])
            continue

        extracted = _extract_with_claude(html, job, claude)
        if not extracted:
            continue

        filled = _fill_empty(job, extracted)
        if filled:
            log.info(
                "[ENRICH] %s [%d/%d]: filled %s for %r",
                site_name, idx, len(to_fetch), filled, job.job_title[:40],
            )
        else:
            log.info(
                "[ENRICH] %s [%d/%d]: no new fields filled for %r",
                site_name, idx, len(to_fetch), job.job_title[:40],
            )

    return jobs
