from __future__ import annotations

import logging
import ssl
from typing import Any
from urllib.parse import urljoin

import httpx

from domain.job import Job
from scraping.strategies.claude_fallback_scraper import scrape_claude_fallback
from scraping.strategies.json_api_scraper import fetch_json_api

log = logging.getLogger(__name__)

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


async def fetch_site_html(site_name: str, url: str) -> dict[str, Any]:
    timeout = httpx.Timeout(30.0, connect=10.0)
    verify: bool | ssl.SSLContext = True
    if site_name in SSL_SKIP_VERIFY_SITES:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        ssl_context.set_ciphers("DEFAULT:@SECLEVEL=1")
        verify = ssl_context

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=DEFAULT_HEADERS,
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


async def scrape_all(
    sites_config: dict[str, Any],
    sites_filter: str,
    claude: Any,
) -> list[Job]:
    filter_list = None if sites_filter.strip().lower() == "all" else [s.strip() for s in sites_filter.split(",")]
    all_jobs: list[Job] = []

    for site_name, config in sites_config.items():
        if filter_list and site_name not in filter_list:
            continue

        log.info("━━ Scraping: %s (%s)", site_name, config.get("mode", "?"))
        try:
            api_endpoint = config.get("api_endpoint")
            if api_endpoint:
                try:
                    api_items = await fetch_json_api(api_endpoint, params=config.get("api_params"))
                    jobs = _normalize_json_jobs(site_name, config, api_items)
                    if jobs:
                        log.info("  ✓ %d listings collected from %s via JSON API", len(jobs), site_name)
                        all_jobs.extend(jobs)
                        continue
                    log.warning("  JSON API returned no usable jobs for %s, falling back to HTML", site_name)
                except Exception as exc:
                    log.warning("  JSON API fetch failed for %s: %s — falling back to HTML", site_name, exc)

            fetch_result = await fetch_site_html(site_name, config["url"])
            html = fetch_result["html"]
            if not html:
                raise ValueError(f"Empty HTML response (status={fetch_result['status']})")

            jobs = await scrape_claude_fallback(html, site_name, config, claude)
            log.info(
                "  ✓ %d listings collected from %s (status=%s, bytes=%d)",
                len(jobs),
                site_name,
                fetch_result["status"],
                len(html),
            )
            all_jobs.extend(jobs)
        except Exception as exc:
            log.error("  ✗ Failed %s: %s", site_name, exc)

    return all_jobs
