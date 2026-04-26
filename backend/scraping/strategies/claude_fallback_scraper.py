from __future__ import annotations

import json
import logging
import re
from typing import Any

from domain.job import Job

log = logging.getLogger(__name__)


async def scrape_claude_fallback(page, site_name: str, config: dict[str, Any], claude: Any) -> list[Job]:
    if not claude:
        log.warning("  No ANTHROPIC_API_KEY — skipping claude_fallback for %s", site_name)
        return []

    html = await page.content()
    body = None
    for pattern in [
        r"<main[\s>].*?</main>",
        r"<article[\s>].*?</article>",
        r'<div[^>]+id=["\']content["\'][^>]*>.*?</div>',
        r'<div[^>]+class=["\'][^"\']*content[^"\']*["\'][^>]*>.*?</div>',
    ]:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match and len(match.group(0)) > 500:
            body = match.group(0)
            break

    if not body:
        body = re.sub(r"<head[\s>].*?</head>", "", html, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<script[\s>].*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<style[\s>].*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<nav[\s>].*?</nav>", "", body, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<footer[\s>].*?</footer>", "", body, flags=re.DOTALL | re.IGNORECASE)

    body = body[:25_000]
    log.info("  Sending %d chars to Claude for extraction …", len(body))

    try:
        response = claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4000,
            system="""You extract job listings from Japanese healthcare website HTML.
This may be a job board listing page with many cards, or a hospital career page.
Extract EVERY job listing you can find on the page.

For each listing, look for:
- job_title: the position name (職種, ポジション)
- facility_name: the hospital/clinic/facility name (施設名, 事業所名)
- location: address or area (勤務地, 所在地) — include prefecture, city, address
- job_description: description of the role (仕事内容)
- requirements: qualifications needed (応募資格, 必要資格)
- salary_raw: salary info as written (給与, 月給, 年収, 時給)
- employment_type: 正社員, パート, 契約社員, etc. (雇用形態)
- application_deadline: deadline if listed (応募期限)
- contact_information: contact details (連絡先)
- url: link to the detail page (make it absolute if possible using the site URL provided)

Return ONLY a valid JSON array. No markdown, no explanation.
Use null for any field you cannot find.
If there are no job listings on the page, return an empty array: []""",
            messages=[{"role": "user", "content": f"Site: {config['url']}\n\nHTML:\n{body}"}],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        listings = json.loads(raw)
        log.info("  Claude extracted %d listings", len(listings))

        return [
            Job(
                source=site_name,
                mode="claude_fallback",
                job_title=item.get("job_title") or "",
                facility_name=item.get("facility_name") or "",
                location=item.get("location") or "",
                job_description=item.get("job_description") or "",
                requirements=item.get("requirements") or "",
                salary_raw=item.get("salary_raw") or "",
                employment_type=item.get("employment_type") or "",
                application_deadline=item.get("application_deadline") or "",
                contact_information=item.get("contact_information") or "",
                url=item.get("url") or "",
            )
            for item in listings
        ]
    except Exception as exc:
        log.error("  Claude extraction failed: %s", exc)
        return []
