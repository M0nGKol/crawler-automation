from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any
from urllib.parse import urlparse

from domain.job import Job
from scraping.extractors import get_href, get_text

log = logging.getLogger(__name__)


async def scrape_css(page, site_name: str, config: dict[str, Any], claude: Any) -> list[Job]:
    selectors = config["selectors"]
    pagination = config.get("pagination", {})
    max_pages = pagination.get("max_pages", 1)
    next_selector = pagination.get("next_selector", "")
    jobs: list[Job] = []

    for page_num in range(max_pages):
        log.info("  Page %d …", page_num + 1)
        await asyncio.sleep(random.uniform(2, 4))

        cards = await page.query_selector_all(selectors.get("card", "article"))
        log.info("  Found %d cards", len(cards))

        for card in cards:
            title = await get_text(card, selectors.get("job_title"))
            facility = await get_text(card, selectors.get("facility_name"))
            location = await get_text(card, selectors.get("location"))
            description = await get_text(card, selectors.get("job_description"))
            requirements = await get_text(card, selectors.get("requirements"))
            salary = await get_text(card, selectors.get("salary"))
            employment_type = await get_text(card, selectors.get("employment_type"))
            deadline = await get_text(card, selectors.get("application_deadline"))
            contact = await get_text(card, selectors.get("contact_information"))
            href = await get_href(card, selectors.get("job_url"))

            if not title and not facility:
                continue

            if href and href.startswith("/"):
                parsed = urlparse(config["url"])
                href = f"{parsed.scheme}://{parsed.netloc}{href}"

            jobs.append(
                Job(
                    source=site_name,
                    mode="css_selectors",
                    job_title=title,
                    facility_name=facility,
                    location=location,
                    job_description=description,
                    requirements=requirements,
                    salary_raw=salary,
                    employment_type=employment_type,
                    application_deadline=deadline,
                    contact_information=contact,
                    url=href,
                )
            )

        if not next_selector:
            break
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.0)

            next_button = await page.query_selector(next_selector)
            if not next_button:
                log.info("  No next page found — stopping pagination")
                break

            await next_button.click()
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            card_selector = selectors.get("card", "article")
            await page.wait_for_selector(card_selector, timeout=10_000)
            await asyncio.sleep(random.uniform(3.0, 5.0))
        except Exception as exc:
            log.warning("  Pagination failed on page %d: %s — stopping", page_num + 1, exc)
            break

    if claude and jobs:
        enrich_limit = config.get("enrich_limit", 10)
        to_enrich = [job for job in jobs if job.url and not job.job_description][:enrich_limit]
        if to_enrich:
            log.info("  Enriching %d jobs from detail pages …", len(to_enrich))
            for idx, job in enumerate(to_enrich):
                detail_page = None
                try:
                    detail_page = await page.context.new_page()
                    await detail_page.goto(job.url, wait_until="domcontentloaded", timeout=20_000)
                    await asyncio.sleep(random.uniform(1.5, 3))

                    detail_html = await detail_page.content()
                    main_match = re.search(
                        r"<main[\s>].*?</main>",
                        detail_html,
                        re.DOTALL | re.IGNORECASE,
                    )
                    body_text = main_match.group(0) if main_match else detail_html
                    body_text = body_text[:15_000]

                    resp = claude.messages.create(
                        model="claude-haiku-4-5",
                        max_tokens=1500,
                        system="""You extract structured data from a Japanese job detail page.
Return ONLY a valid JSON object (NOT an array). No markdown, no explanation.
Keys (use null if not found):
  job_description       — full description of the role
  requirements          — qualifications, certifications, experience needed
  employment_type       — 正社員, パート, 契約社員, etc.
  application_deadline  — deadline date if listed
  contact_information   — phone, email, or department to contact""",
                        messages=[{"role": "user", "content": f"URL: {job.url}\n\nHTML:\n{body_text}"}],
                    )

                    raw_resp = resp.content[0].text.strip()
                    raw_resp = re.sub(r"^```[a-z]*\n?", "", raw_resp)
                    raw_resp = re.sub(r"\n?```$", "", raw_resp)
                    detail = json.loads(raw_resp)

                    job.job_description = detail.get("job_description") or ""
                    job.requirements = detail.get("requirements") or ""
                    job.employment_type = detail.get("employment_type") or ""
                    job.application_deadline = detail.get("application_deadline") or ""
                    job.contact_information = detail.get("contact_information") or ""

                    log.info("    [%d/%d] Enriched: %s", idx + 1, len(to_enrich), job.job_title[:40])
                except Exception as exc:
                    log.warning("    [%d/%d] Enrich failed: %s", idx + 1, len(to_enrich), exc)
                finally:
                    if detail_page:
                        await detail_page.close()

    return jobs
