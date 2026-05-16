from __future__ import annotations

import asyncio
import logging
import ssl
import time
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from domain.job import Job
from scraping.strategies.claude_fallback_scraper import scrape_claude_fallback
from scraping.strategies.detail_enricher import enrich_jobs_with_detail_pages
from scraping.strategies.json_api_scraper import fetch_json_api

log = logging.getLogger(__name__)

TIMEOUTS = {
    "default": 60,
    "hospital_site": 45,
    "job_board": 90,
}

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

SSL_SKIP_VERIFY_SITES = {
    "tokyo_university_hospital",
    "tokyo_medical_university",
}

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


async def fetch_site_html(site_name: str, url: str, timeout_seconds: int = 30, custom_headers: dict[str, str] | None = None) -> dict[str, Any]:
    timeout = httpx.Timeout(float(timeout_seconds), connect=min(10.0, float(timeout_seconds)))
    verify: bool | ssl.SSLContext = True
    if site_name in SSL_SKIP_VERIFY_SITES:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        ssl_context.set_ciphers("DEFAULT:@SECLEVEL=1")
        verify = ssl_context

    headers = custom_headers if custom_headers else DEFAULT_HEADERS

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        http2=True,
        verify=verify,
    ) as client:
        response = await client.get(url)
        return {
            "html": response.text,
            "status": response.status_code,
            "url": str(response.url),
        }


def _site_timeout(config: dict[str, Any]) -> int:
    site_type = str(config.get("type", "")).strip()
    return int(TIMEOUTS.get(site_type, TIMEOUTS["default"]))


def _site_result(
    site_name: str,
    status: str,
    jobs: list[Job] | None = None,
    *,
    error: str = "",
    fetch_method: str = "",
    attempts: int = 0,
    duration_ms: int = 0,
    status_code: int | None = None,
) -> dict[str, Any]:
    jobs = jobs or []
    result: dict[str, Any] = {
        "site": site_name,
        "status": status,
        "jobs": jobs,
        "job_count": len(jobs),
        "attempts": attempts,
        "duration_ms": duration_ms,
    }
    if error:
        result["error"] = error
    if fetch_method:
        result["fetch_method"] = fetch_method
    if status_code is not None:
        result["status_code"] = status_code
    return result


def _pick(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            value = " / ".join(str(item).strip() for item in value if str(item).strip())
        value = str(value).strip()
        if value:
            return value
    return ""


def _normalize_json_jobs(site_name: str, config: dict[str, Any], items: list[dict[str, Any]]) -> list[Job]:
    jobs: list[Job] = []

    for item in items:
        detail_url = _pick(item, "url", "job_url", "detail_url", "link", "detailPath", "path")
        if detail_url and not detail_url.startswith(("http://", "https://")):
            detail_url = urljoin(config["url"], detail_url)

        jobs.append(
            Job(
                source=site_name,
                mode="json_api",
                job_title=_pick(item, "job_title", "title", "name", "occupation_name"),
                facility_name=_pick(item, "facility_name", "office_name", "company_name", "hospital_name", "client_name"),
                location=_pick(item, "location", "address", "city", "work_location", "prefecture_name"),
                job_description=_pick(item, "job_description", "description", "work_description", "catch_copy"),
                requirements=_pick(item, "requirements", "requirement", "required_qualification", "qualification"),
                salary_raw=_pick(item, "salary_raw", "salary", "salary_text", "wage", "annual_salary"),
                employment_type=_pick(item, "employment_type", "employment_status", "contract_type", "job_type"),
                application_deadline=_pick(item, "application_deadline", "deadline", "closing_date"),
                contact_information=_pick(item, "contact_information", "contact", "contact_name"),
                url=detail_url,
            )
        )

    return [job for job in jobs if job.job_title or job.raw_facility or job.url]


def _scrape_jobmedley_html(html: str, site_name: str, url: str) -> list[Job]:
    """Scrape Job Medley site using BeautifulSoup HTML parsing."""
    jobs: list[Job] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        # Job Medley listings are in <a> tags with class like "job-list-item" or similar
        job_elements = soup.find_all("a", class_=lambda x: x and "job" in x.lower())

        if not job_elements:
            # Fallback: look for links containing job info
            job_elements = soup.find_all("a", href=lambda x: x and "/job/" in x.lower())

        for elem in job_elements:
            title = elem.get_text(strip=True)
            href = elem.get("href", "")

            if not title or not href:
                continue

            # Make relative URLs absolute
            if href and not href.startswith(("http://", "https://")):
                href = urljoin(url, href)

            if title and href:
                jobs.append(
                    Job(
                        source=site_name,
                        mode="html_beautifulsoup",
                        job_title=title,
                        facility_name="",
                        location="",
                        job_description="",
                        requirements="",
                        salary_raw="",
                        employment_type="",
                        application_deadline="",
                        contact_information="",
                        url=href,
                    )
                )
    except Exception as exc:
        log.error("  BeautifulSoup parsing failed for %s: %s", site_name, exc)

    return jobs


async def scrape_site(
    site_name: str,
    config: dict[str, Any],
    claude: Any,
    should_stop: "callable | None" = None,
) -> dict[str, Any]:
    fetch_method = "html"

    # Special handling for Job Medley — skip JSON API, use BeautifulSoup instead
    if site_name.startswith("jobmedley"):
        fetch_result = await fetch_site_html(site_name, config["url"], timeout_seconds=_site_timeout(config))
        html = fetch_result["html"]
        if not html:
            raise ValueError(f"Empty HTML response (status={fetch_result['status']})")

        jobs = _scrape_jobmedley_html(html, site_name, config["url"])
        if not jobs:
            log.warning("  BeautifulSoup found no jobs for %s, trying Claude fallback", site_name)
            jobs = await scrape_claude_fallback(html, site_name, config, claude)
            fetch_method = "beautifulsoup_fallback_claude"
        else:
            fetch_method = "beautifulsoup"

        # Pass 2: visit each listing's detail page to fill missing fields
        # (description, requirements, deadline, contact, full salary).
        if jobs:
            jobs = await enrich_jobs_with_detail_pages(jobs, site_name, claude, should_stop=should_stop)

        log.info(
            "  ✓ %d listings collected from %s (status=%s, method=%s, bytes=%d)",
            len(jobs),
            site_name,
            fetch_result["status"],
            fetch_method,
            len(html),
        )
        return _site_result(
            site_name,
            "success" if jobs else "no_jobs",
            jobs,
            fetch_method=fetch_method,
            status_code=fetch_result["status"],
        )

    # Special handling for GUBBY_DR (guppy.jp) — JS-rendered site, needs browser
    if site_name.startswith("gubby"):
        browser_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://guppy.jp/",
        }
        fetch_result = await fetch_site_html(site_name, config["url"], timeout_seconds=_site_timeout(config), custom_headers=browser_headers)
        html = fetch_result["html"]
        log.info("  [GUBBY_DR] fetched %d bytes from %s", len(html), site_name)
        log.debug("  [GUBBY_DR] first 500 chars: %s", html[:500])

        if not html or len(html) < 500:
            log.info("  [SKIP] %s - JS rendered site, needs Playwright", site_name)
            return _site_result(site_name, "skipped", [], error="JS rendered site requires Playwright", status_code=fetch_result["status"])

        if html.count("<script") > 10 and html.count("</body>") < 2:
            log.info("  [SKIP] %s - JS rendered site, needs Playwright", site_name)
            return _site_result(site_name, "skipped", [], error="JS rendered site requires Playwright", status_code=fetch_result["status"])

    # Standard flow for other sites
    api_endpoint = config.get("api_endpoint")
    if api_endpoint:
        try:
            api_items = await fetch_json_api(api_endpoint, params=config.get("api_params"))
            jobs = _normalize_json_jobs(site_name, config, api_items)
            if jobs:
                log.info("  ✓ %d listings collected from %s via JSON API", len(jobs), site_name)
                return _site_result(site_name, "success", jobs, fetch_method="json_api", status_code=200)
            log.warning("  JSON API returned no usable jobs for %s, falling back to HTML", site_name)
            fetch_method = "json_api_fallback"
        except Exception as exc:
            log.warning("  JSON API fetch failed for %s: %s — falling back to HTML", site_name, exc)
            fetch_method = "json_api_fallback"

    fetch_result = await fetch_site_html(site_name, config["url"], timeout_seconds=_site_timeout(config))
    html = fetch_result["html"]
    if not html:
        raise ValueError(f"Empty HTML response (status={fetch_result['status']})")

    jobs = await scrape_claude_fallback(html, site_name, config, claude)

    # Pass 2: visit each listing's detail page to fill missing fields.
    # This is what gives you the "full information from the page you view"
    # rather than just the listing card snippet.
    if jobs:
        jobs = await enrich_jobs_with_detail_pages(jobs, site_name, claude, should_stop=should_stop)

    log.info(
        "  ✓ %d listings collected from %s (status=%s, bytes=%d)",
        len(jobs),
        site_name,
        fetch_result["status"],
        len(html),
    )
    return _site_result(
        site_name,
        "success" if jobs else "no_jobs",
        jobs,
        fetch_method=fetch_method,
        status_code=fetch_result["status"],
    )


async def scrape_with_retry(
    site_name: str,
    config: dict[str, Any],
    claude: Any,
    max_retries: int = MAX_RETRIES,
    backoff: int = RETRY_BACKOFF_SECONDS,
    should_stop: "callable | None" = None,
) -> dict[str, Any]:
    """Run scrape_site with retry policy.

    Retry only on TRANSIENT failures (timeout, exception). If the fetch succeeded
    but parsing yielded 0 jobs (status="no_jobs"), that's a STRUCTURAL failure —
    retrying with the same fetcher will deterministically fail the same way and
    just burns ScraperAPI credits / Claude API calls. Return immediately in that
    case so we don't waste 2× extra attempts per site.
    """
    last_error = ""
    timeout_seconds = _site_timeout(config)
    started_at = time.monotonic()

    for attempt in range(1, max_retries + 1):
        if should_stop and should_stop():
            log.info("%s stopped by user before attempt %d", site_name, attempt)
            return _site_result(
                site_name, "stopped", [],
                error="stopped by user",
                attempts=attempt - 1,
                duration_ms=int((time.monotonic() - started_at) * 1000),
            )
        try:
            result = await asyncio.wait_for(
                scrape_site(site_name, config, claude, should_stop=should_stop),
                timeout=timeout_seconds,
            )
            result["attempts"] = attempt
            result["duration_ms"] = int((time.monotonic() - started_at) * 1000)
            if result.get("jobs"):
                return result
            if result.get("status") == "skipped":
                return result
            # Structural failure: fetch succeeded but parser/Claude found nothing.
            # Retrying won't help — the page just doesn't render jobs server-side
            # (likely a JS-only SPA or layout change). Don't burn more credits.
            if result.get("status") == "no_jobs":
                log.warning(
                    "%s: 0 jobs after fetch succeeded — not retrying (structural failure, would waste credits)",
                    site_name,
                )
                result["error"] = "no_jobs (no retry — structural)"
                return result
            last_error = "no jobs found"
            log.warning("%s attempt %d: no jobs found, retrying...", site_name, attempt)
        except asyncio.TimeoutError:
            last_error = "timeout"
            log.warning("%s attempt %d: timeout", site_name, attempt)
        except Exception as exc:
            last_error = str(exc)
            log.warning("%s attempt %d: %s", site_name, attempt, exc)

        if attempt < max_retries:
            await asyncio.sleep(backoff * attempt)

    log.error("%s failed after %d attempts: %s", site_name, max_retries, last_error)
    final_status = "timeout" if last_error == "timeout" else "failed"
    return _site_result(
        site_name,
        final_status,
        [],
        error=last_error,
        attempts=max_retries,
        duration_ms=int((time.monotonic() - started_at) * 1000),
    )


async def scrape_all(
    sites_config: dict[str, Any],
    sites_filter: str,
    claude: Any,
    should_stop: "callable | None" = None,
) -> tuple[list[Job], list[dict[str, Any]]]:
    filter_list = None if sites_filter.strip().lower() == "all" else [s.strip() for s in sites_filter.split(",")]
    all_jobs: list[Job] = []
    site_results: list[dict[str, Any]] = []

    for site_name, config in sites_config.items():
        if filter_list and site_name not in filter_list:
            continue

        # Cooperative cancellation: check before starting each site
        if should_stop and should_stop():
            log.info("Pipeline stopped by user — skipping remaining sites starting at %s", site_name)
            site_results.append(_site_result(site_name, "stopped", [], error="stopped by user"))
            continue

        log.info("━━ Scraping: %s (%s)", site_name, config.get("mode", "?"))
        try:
            result = await scrape_with_retry(site_name, config, claude, should_stop=should_stop)
        except Exception as exc:
            log.error("%s failed: %s", site_name, exc)
            result = _site_result(site_name, "failed", [], error=str(exc))
        site_results.append(result)
        all_jobs.extend(result.get("jobs", []))

    return all_jobs, site_results
