import os
import hashlib
import logging
import re
from datetime import datetime
import xml.etree.ElementTree as ET

import requests

from domain.job import Job

log = logging.getLogger(__name__)

SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")

SEARCH_QUERIES = [
    {"q": "看護師", "l": "東京"},
    {"q": "医師", "l": "東京"},
    {"q": "薬剤師", "l": "東京"},
]

# ── Credit-saving limits ──────────────────────────────────────────────────────
# How many jobs to pull per RSS query. Lower = fewer detail-page requests.
RSS_LIMIT_PER_QUERY: int = int(os.getenv("INDEED_RSS_LIMIT", "15"))

# Hard cap on ScraperAPI detail-page calls per full pipeline run.
# render=true costs 5-10× more credits; this keeps a run predictable.
#
# DEFAULT = 0 (disabled). Indeed Japan's viewjob pages are behind Cloudflare;
# in practice BOTH render=false and render=true consistently fail validation,
# wasting 6-11 credits per detail attempt with zero data extracted. Keep this
# disabled unless you upgrade ScraperAPI to premium=true / ultra_premium=true.
# Set INDEED_MAX_DETAIL_FETCHES=20 in env to re-enable enrichment.
MAX_DETAIL_FETCHES: int = int(os.getenv("INDEED_MAX_DETAIL_FETCHES", "0"))

# Circuit breaker: abort the rest of the enrichment pass after this many
# consecutive failures. Stops the bleeding when Cloudflare is blocking every
# request — saves ~150 credits/run when ScraperAPI can't get through.
ENRICHMENT_FAILURE_CIRCUIT_BREAKER: int = int(os.getenv("INDEED_ENRICHMENT_CIRCUIT", "3"))

# Fields that must be populated for a job to skip the detail-page fetch.
_ENRICHMENT_FIELDS = ("requirements", "employment_type", "application_deadline", "job_description")


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def fetch_url(url: str, use_proxy: bool = False, render_js: bool = False) -> requests.Response:
    """Fetch URL directly or via ScraperAPI.

    render_js=True should be used for detail pages — Indeed Japan's job pages
    are protected by Cloudflare and require JavaScript execution to serve real HTML.
    render_js=False is fine for listing/search pages and RSS feeds.
    """
    if use_proxy and SCRAPERAPI_KEY:
        log.info(f"[INDEED] ScraperAPI (render={render_js}) for: {url}")
        return requests.get(
            "http://api.scraperapi.com",
            params={
                "api_key": SCRAPERAPI_KEY,
                "url": url,
                "country_code": "jp",
                "render": "true" if render_js else "false",
            },
            timeout=60,  # JS rendering needs extra time
        )

    log.info(f"[INDEED] Direct fetch: {url}")
    return requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RSS reader)"},
        timeout=30,
    )


def _normalize_indeed_url(url: str) -> str:
    """
    Convert any Indeed URL variant to a canonical viewjob URL.
    Returns an empty string for URLs that cannot be enriched (e.g. ad trackers).

    URL types encountered in the wild:
      /rc/clk?jk=ABC123&...          — organic click tracker, has jk param → OK
      /viewjob?jk=ABC123             — canonical, already good → OK
      /pagead/clk?mo=r&ad=...        — paid ad tracker, NO jk param, 500s on fetch → SKIP
      /pagead/googleclk?...          — same, Google-served ad → SKIP
    """
    if not url:
        return ""
    if not url.startswith("http"):
        url = f"https://jp.indeed.com{url}"

    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)

    # Sponsored ad tracking URLs — ScraperAPI returns 500, no job key available.
    # Returning "" signals to the caller that enrichment should be skipped.
    if any(seg in parsed.path for seg in ("/pagead/clk", "/pagead/googleclk", "/pagead/")):
        log.debug(f"[INDEED] Skipping ad-tracker URL (no job key): {url[:80]}")
        return ""

    params = parse_qs(parsed.query)
    jk = params.get("jk", [None])[0]
    if jk:
        return f"https://jp.indeed.com/viewjob?jk={jk}"

    # Unknown URL format — return as-is and let the fetch attempt decide
    return url


def _is_valid_job_page(html: str) -> bool:
    """
    Return True only if the HTML looks like a real Indeed job detail page.
    Rejects Cloudflare challenge pages, empty responses, and error pages.
    """
    if not html or len(html) < 500:
        return False
    # Cloudflare / bot detection markers
    if any(marker in html for marker in [
        "challenge-platform",
        "cf-browser-verification",
        "Just a moment",
        "Checking your browser",
        "Enable JavaScript",
        "cf_chl_",
    ]):
        return False
    # Must contain at least one indicator that this is a real Indeed page
    return any(marker in html for marker in [
        "jobDescriptionText",
        "jobsearch-JobComponent",
        "viewJobSSRRoot",
        "jobDescription",
        "icl-u-xs",
        "雇用形態",
        "給与",
        "勤務地",
    ])


# ── Two-pass detail enrichment ────────────────────────────────────────────────

def _needs_enrichment(job: Job) -> bool:
    """Return True if any critical field is still empty — triggers a detail fetch."""
    return any(not getattr(job, field, "") for field in _ENRICHMENT_FIELDS)


def _enrich_jobs(jobs: list[Job]) -> list[Job]:
    """
    Pass 2: visit each job's detail page to fill empty fields.

    Credit-saving rules applied here:
    1. Skip jobs that already have complete data (free).
    2. Hard cap: at most MAX_DETAIL_FETCHES ScraperAPI calls per run.
    3. Each call tries render=false first (1 credit); only upgrades to
       render=true (5-10 credits) if the response fails validation.
       In practice, Indeed Japan embeds all structured data in JSON-LD
       which is SSR-rendered — so render=false is usually sufficient.
    4. Circuit breaker: after N consecutive failures, abort the rest of
       the pass. Indeed Japan often Cloudflare-blocks every request — once
       that pattern is established, retrying just burns credits.
    """
    if MAX_DETAIL_FETCHES == 0:
        log.info("[INDEED] Enrichment disabled (INDEED_MAX_DETAIL_FETCHES=0) — RSS fields only")
        return jobs

    needs = [j for j in jobs if _needs_enrichment(j)]
    complete = len(jobs) - len(needs)
    to_fetch = needs[:MAX_DETAIL_FETCHES]
    capped = len(needs) - len(to_fetch)

    log.info(
        f"[INDEED] Enrichment pass: {len(to_fetch)} detail fetches "
        f"(+{complete} already complete, +{capped} skipped by cap)"
    )

    consecutive_failures = 0
    fetched = 0
    aborted = False
    for job in to_fetch:
        ok = _enrich_job_from_detail(job)
        fetched += 1
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= ENRICHMENT_FAILURE_CIRCUIT_BREAKER:
                log.error(
                    "[INDEED] Circuit breaker tripped after %d consecutive failures — "
                    "aborting enrichment for this run (saved %d further attempts)",
                    consecutive_failures,
                    len(to_fetch) - fetched,
                )
                aborted = True
                break

    if not aborted:
        log.info("[INDEED] Enrichment pass complete: %d attempts", fetched)
    return jobs


def _enrich_job_from_detail(job: Job) -> bool:
    """
    Fetch the job detail page and extract missing fields. Mutates in-place.

    Returns True if any data was extracted, False if both fetch attempts failed
    or the URL was skippable. The caller uses this for circuit-breaker logic.

    Credit strategy (cheapest-first):
    1. Try render=false (1 credit) — JSON-LD structured data is SSR-rendered
       on Indeed Japan viewjob pages and doesn't need JavaScript.
    2. If the page fails the validity check (Cloudflare challenge), upgrade to
       render=true (5-10 credits) as a last resort.
    3. If both fail, log a warning and leave the fields empty.
    """
    if not job.url:
        return False

    # Normalize redirect URLs (e.g. /rc/clk?jk=...) to canonical viewjob URLs.
    # Returns "" for ad-tracker URLs (/pagead/clk) that cannot be enriched.
    canonical_url = _normalize_indeed_url(job.url)
    if not canonical_url:
        log.info(f"[INDEED] Skipping enrichment — ad-tracker URL: {job.url[:80]}")
        # Don't count "skipped because unfetchable URL" as a circuit-breaker failure.
        return True
    if canonical_url != job.url:
        log.info(f"[INDEED] URL normalized: {job.url[:60]} → {canonical_url}")
        job.url = canonical_url

    html: str = ""
    try:
        # ── Attempt 1: render=false (cheap, 1 credit) ───────────────────────
        resp = fetch_url(canonical_url, use_proxy=True, render_js=False)
        if resp.status_code == 200 and _is_valid_job_page(resp.text):
            html = resp.text
            log.info(f"[INDEED] Detail OK with render=false (cheap): {canonical_url}")
        else:
            # ── Attempt 2: render=true (expensive, 5-10 credits) ────────────
            log.info(f"[INDEED] render=false invalid ({resp.status_code}), upgrading to render=true: {canonical_url}")
            resp2 = fetch_url(canonical_url, use_proxy=True, render_js=True)
            if resp2.status_code == 200 and _is_valid_job_page(resp2.text):
                html = resp2.text
                log.info(f"[INDEED] Detail OK with render=true: {canonical_url}")
            else:
                log.warning(f"[INDEED] Both render attempts failed for: {canonical_url}")
                return False
    except Exception as e:
        log.warning(f"[INDEED] Detail fetch failed for {canonical_url}: {e}")
        return False

    extracted = _extract_detail_fields(html)

    # Only overwrite fields that are currently empty on the job object
    if not job.job_description and extracted.get("job_description"):
        job.job_description = extracted["job_description"]
    if not job.requirements and extracted.get("requirements"):
        job.requirements = extracted["requirements"]
    if not job.employment_type and extracted.get("employment_type"):
        job.employment_type = extracted["employment_type"]
    if not job.application_deadline and extracted.get("application_deadline"):
        job.application_deadline = extracted["application_deadline"]
    if not job.contact_information and extracted.get("contact_information"):
        job.contact_information = extracted["contact_information"]
    if not job.salary_raw and extracted.get("salary_raw"):
        job.salary_raw = extracted["salary_raw"]

    filled = [f for f in _ENRICHMENT_FIELDS if getattr(job, f, "")]
    log.info(f"[INDEED] Enriched {job.job_title[:40]!r} — filled: {filled}")
    return True


def _extract_from_json_ld(soup) -> dict:
    """
    Extract job fields from JSON-LD structured data embedded in the page.

    Indeed Japan injects a <script type="application/ld+json"> block containing
    a JobPosting schema on every viewjob page for SEO purposes. This is
    server-side rendered so it's available even with render=false (no JS needed).
    This is the cheapest extraction path — 1 credit vs 5-10 for render=true.
    """
    import json

    result: dict = {
        "job_description": "",
        "requirements": "",
        "employment_type": "",
        "application_deadline": "",
        "contact_information": "",
        "salary_raw": "",
    }

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both a single object and an array
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") not in ("JobPosting", "jobPosting"):
                continue

            # Description
            if item.get("description") and not result["job_description"]:
                desc = re.sub(r"<[^>]+>", " ", str(item["description"]))
                result["job_description"] = desc.strip()[:2000]

            # Employment type (may be English like "FULL_TIME" — translate)
            _ET_MAP = {
                "FULL_TIME": "正社員", "PART_TIME": "パート・アルバイト",
                "CONTRACTOR": "契約社員", "TEMPORARY": "派遣社員",
                "INTERN": "インターン", "OTHER": "その他",
            }
            et = item.get("employmentType", "")
            if et and not result["employment_type"]:
                result["employment_type"] = _ET_MAP.get(et.upper(), et)

            # Application deadline
            if item.get("validThrough") and not result["application_deadline"]:
                result["application_deadline"] = str(item["validThrough"])[:20]

            # Salary
            base = item.get("baseSalary", {})
            if base and not result["salary_raw"]:
                val = base.get("value", {})
                if isinstance(val, dict):
                    mn = val.get("minValue", "")
                    mx = val.get("maxValue", "")
                    unit_map = {"HOUR": "時給", "DAY": "日給", "WEEK": "週給", "MONTH": "月給", "YEAR": "年収"}
                    unit = unit_map.get(str(val.get("unitText", "")).upper(), "")
                    currency = base.get("currency", "JPY")
                    if mn and mx:
                        result["salary_raw"] = f"{unit}{mn}〜{mx}{currency}"
                    elif mn or mx:
                        result["salary_raw"] = f"{unit}{mn or mx}{currency}"
                elif val:
                    result["salary_raw"] = str(val)

            # Hiring org contact
            org = item.get("hiringOrganization", {})
            if isinstance(org, dict) and not result["contact_information"]:
                contact_parts = [p for p in [
                    org.get("name", ""),
                    org.get("telephone", ""),
                    org.get("email", ""),
                ] if p]
                if contact_parts:
                    result["contact_information"] = " / ".join(contact_parts)[:200]

            log.debug(f"[INDEED] JSON-LD extracted: {list(k for k,v in result.items() if v)}")
            return result  # found a JobPosting — done

    return result  # no JSON-LD found or no matching @type


def _extract_detail_fields(html: str) -> dict:
    """
    Parse an Indeed Japan job detail page and extract all structured fields.

    Strategy (cheapest-first):
    1. JSON-LD structured data  — SSR, works with render=false, zero extra cost
    2. CSS selector fallbacks   — SSR div elements
    3. Full-text regex          — last resort

    Returns a dict — missing fields are empty strings.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # ── Strategy 1: JSON-LD (cheapest, most reliable) ────────────────────────
    result = _extract_from_json_ld(soup)

    # If JSON-LD gave us everything we need, return immediately
    if all(result.get(f) for f in ("job_description", "employment_type")):
        log.info("[INDEED] Extraction complete via JSON-LD (no CSS/regex needed)")
        return result

    # ── Strategy 2 & 3: CSS + regex fallback for still-empty fields ──────────
    # (only runs when JSON-LD was missing or incomplete)

    # ── Job Description ───────────────────────────────────────────────────────
    # Indeed Japan uses id="jobDescriptionText" on its SSR-rendered viewjob pages.
    desc_el = (
        soup.find("div", id="jobDescriptionText")
        or soup.find("div", attrs={"data-testid": "jobsearch-JobComponent-description"})
        or soup.find("div", class_=re.compile(r"jobDescription|jobsearch-jobDescriptionText", re.I))
        or soup.find("div", id=re.compile(r"jobDescription", re.I))
    )
    if desc_el:
        result["job_description"] = desc_el.get_text(separator="\n", strip=True)[:2000]

    # ── Salary ────────────────────────────────────────────────────────────────
    # viewjob pages put salary in a metadata table or attribute_snippet span.
    salary_candidates = (
        soup.find_all(attrs={"data-testid": "attribute_snippet_testid"})
        + soup.find_all("div", class_=re.compile(r"salary|wage", re.I))
        + soup.find_all("span", class_=re.compile(r"salary|icl-u-xs", re.I))
        + soup.find_all("div", class_=re.compile(r"icl-u-xs", re.I))
    )
    for el in salary_candidates:
        text = el.get_text(strip=True)
        if any(c in text for c in ["円", "万", "¥", "時給", "月給", "年収"]):
            result["salary_raw"] = text[:200]
            break

    full_text = soup.get_text(separator="\n")

    # ── Employment Type ───────────────────────────────────────────────────────
    # First try structured metadata rows (viewjob pages render these as labelled divs)
    employment_el = soup.find(string=re.compile(r"雇用形態|勤務形態"))
    if employment_el:
        parent = employment_el.find_parent()
        if parent:
            # Sibling or parent's next sibling typically holds the value
            sibling = parent.find_next_sibling()
            if sibling:
                result["employment_type"] = sibling.get_text(strip=True)[:100]
    if not result["employment_type"]:
        employment_keywords = ["正社員", "パート", "アルバイト", "契約社員", "派遣社員", "業務委託", "嘱託"]
        for keyword in employment_keywords:
            if keyword in full_text:
                match = re.search(
                    rf"(雇用形態|勤務形態)[^\n]*{keyword}|{keyword}[^\n]*(雇用|勤務|契約)",
                    full_text,
                )
                result["employment_type"] = match.group(0).strip()[:100] if match else keyword
                break

    # ── Application Deadline ──────────────────────────────────────────────────
    deadline_patterns = [
        r"応募締切[^\n：:]*[:：]?\s*([^\n]+)",
        r"募集期間[^\n：:]*[:：]?\s*([^\n]+)",
        r"締切[^\n：:]*[:：]?\s*(\d{4}[年/\-]\d{1,2}[月/\-]\d{1,2})",
        r"(\d{4}年\d{1,2}月\d{1,2}日).*?まで",
        r"(\d{4}/\d{1,2}/\d{1,2}).*?締",
        r"(\d{4}-\d{2}-\d{2}).*?締",
    ]
    for pattern in deadline_patterns:
        match = re.search(pattern, full_text)
        if match:
            captured = (match.group(1) if match.lastindex and match.group(1) else match.group(0))
            result["application_deadline"] = captured.strip()[:100]
            break

    # ── Contact Information ───────────────────────────────────────────────────
    contact_patterns = [
        r"(採用担当[^\n]{0,100})",
        r"(お問い合わせ[^\n]{0,100})",
        r"(TEL[^\n]{0,80})",
        r"(電話[^\n：:]*[:：]?\s*[\d\-（）()]+)",
        r"([\w.+-]+@[\w\-]+\.[a-z]{2,})",
    ]
    for pattern in contact_patterns:
        match = re.search(pattern, full_text)
        if match:
            result["contact_information"] = match.group(1).strip()[:200]
            break

    # ── Requirements ──────────────────────────────────────────────────────────
    # Try structured element first, then regex on full text
    req_el = soup.find(string=re.compile(r"応募資格|必要資格|応募条件|資格要件|必須スキル"))
    if req_el:
        parent = req_el.find_parent()
        if parent:
            block = parent.find_next_sibling() or parent.find_parent()
            if block:
                result["requirements"] = block.get_text(separator="\n", strip=True)[:500]
    if not result["requirements"]:
        req_patterns = [
            r"応募資格\s*([^\n].{10,500}?)(?=\n\n|\Z)",
            r"必要資格\s*([^\n].{10,500}?)(?=\n\n|\Z)",
            r"応募条件\s*([^\n].{10,500}?)(?=\n\n|\Z)",
            r"資格要件\s*([^\n].{10,500}?)(?=\n\n|\Z)",
            r"必須スキル\s*([^\n].{10,500}?)(?=\n\n|\Z)",
        ]
        for pattern in req_patterns:
            match = re.search(pattern, full_text, re.DOTALL)
            if match:
                result["requirements"] = match.group(1).strip()[:500]
                break

    return result


# ── Domain model conversion ───────────────────────────────────────────────────

def _dict_jobs_to_domain_jobs(job_dicts: list[dict]) -> list[Job]:
    """Convert the job dictionaries into our internal domain.job.Job objects."""
    jobs: list[Job] = []
    for jd in job_dicts:
        job = Job(
            source=str(jd.get("source", "") or ""),
            mode="scraperapi_with_rss_fallback",
            raw_facility=str(jd.get("raw_facility", "") or ""),
            job_title=str(jd.get("job_title", "") or ""),
            location=str(jd.get("location", "") or ""),
            job_description=str(jd.get("job_description", "") or ""),
            requirements=str(jd.get("requirements", "") or ""),
            salary_raw=str(jd.get("salary_raw", "") or ""),
            employment_type=str(jd.get("employment_type", "") or ""),
            application_deadline=str(jd.get("application_deadline", "") or ""),
            contact_information=str(jd.get("contact_information", "") or ""),
            url=str(jd.get("url", "") or ""),
        )
        # Preserve the deterministic id/scraped_at generated by the scraper
        job.id = str(jd.get("id", job.id))
        scraped_at = jd.get("scraped_at") or None
        if scraped_at:
            job.scraped_at = str(scraped_at)
        jobs.append(job)
    return jobs


# ── Main scrape entry points ──────────────────────────────────────────────────

def scrape_indeed_rss(query: str, location: str) -> list[Job]:
    """
    Pass 1: Try RSS feed first (free, no proxy).
    On block, fall back to ScraperAPI HTML scrape.
    Pass 2: Enrich each job with detail-page fetch for missing fields.
    """
    rss_url = f"https://jp.indeed.com/rss?q={query}&l={location}&limit={RSS_LIMIT_PER_QUERY}"

    try:
        response = fetch_url(rss_url, use_proxy=False)
        if response.status_code == 200 and "<rss" in response.text:
            jobs = _dict_jobs_to_domain_jobs(parse_rss(response.text, query, location))
            return _enrich_jobs(jobs)
        log.warning(f"[INDEED] RSS blocked for {query}/{location} — trying ScraperAPI")
    except Exception as e:
        log.warning(f"[INDEED] RSS failed: {e}")

    # Fallback to ScraperAPI HTML scrape
    try:
        search_url = f"https://jp.indeed.com/jobs?q={query}&l={location}&limit=50"
        response = fetch_url(search_url, use_proxy=True)
        if response.status_code == 200:
            jobs = _dict_jobs_to_domain_jobs(parse_html(response.text, query, location))
            return _enrich_jobs(jobs)
        log.error(f"[INDEED] ScraperAPI also failed: {response.status_code}")
    except Exception as e:
        log.error(f"[INDEED] ScraperAPI failed: {e}")

    return []


def _extract_rss_employment_type(desc_html: str) -> str:
    """Try to find an employment type keyword in an RSS description blob."""
    text = re.sub(r"<[^>]+>", " ", desc_html)
    for keyword in ["正社員", "パート", "アルバイト", "契約社員", "派遣社員", "業務委託", "嘱託"]:
        if keyword in text:
            return keyword
    return ""


def parse_rss(xml_text: str, query: str, location: str) -> list[dict]:
    """Parse Indeed RSS feed into standard job schema.

    Extracts as many fields as possible from the description HTML to reduce
    the number of jobs that need an expensive detail-page fetch in Pass 2.
    """
    jobs: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title = item.find("title")
            link = item.find("link")
            description = item.find("description")

            if not title or not link:
                continue

            desc_html = description.text if description is not None else ""
            desc_text = strip_html(desc_html)

            job_id = hashlib.md5(f"indeed_japan|{title.text}|{location}".encode()).hexdigest()

            jobs.append(
                {
                    "id": job_id,
                    "source": "indeed_japan",
                    "raw_facility": extract_facility(title.text or ""),
                    "masked_facility": "",
                    "job_title": clean_title(title.text or ""),
                    "location": location,
                    # RSS description is a short snippet — enrich_jobs will
                    # expand this only if it's still below threshold
                    "job_description": desc_text[:500],
                    "requirements": "",
                    # Pull salary and employment_type from the RSS blob so
                    # these jobs can skip the detail fetch if that's all
                    # they're missing (saves ScraperAPI credits)
                    "salary_raw": extract_salary(desc_html),
                    "salary_masked": "",
                    "employment_type": _extract_rss_employment_type(desc_html),
                    "application_deadline": "",
                    "contact_information": "",
                    "url": link.text or "",
                    "scraped_at": datetime.utcnow().isoformat(),
                }
            )
    except ET.ParseError as e:
        log.error(f"[INDEED] RSS parse error: {e}")

    log.info(f"[INDEED] RSS parsed {len(jobs)} jobs for {query}/{location}")
    return jobs


def parse_html(html: str, query: str, location: str) -> list[dict]:
    """
    Parse Indeed HTML search results via BeautifulSoup.
    Uses multiple fallback selectors per field to handle Indeed's frequent DOM changes.
    """
    from bs4 import BeautifulSoup

    jobs: list[dict] = []

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Multiple fallback card selectors — Indeed changes class names regularly
        job_cards = (
            soup.find_all("div", class_="job_seen_beacon")
            or soup.find_all("div", {"data-testid": "slider_item"})
            or soup.find_all("li", class_=re.compile(r"job", re.I))
            or soup.find_all("div", class_=re.compile(r"jobCard|job-card|resultContent", re.I))
        )

        log.info(f"[INDEED] Found {len(job_cards)} job cards in HTML")

        for card in job_cards:
            # Title — multiple fallback selectors
            title_el = (
                card.find("span", {"data-testid": "jobTitle"})
                or card.find("span", id=re.compile(r"jobTitle", re.I))
                or card.find("h2", class_=re.compile(r"jobTitle|job-title", re.I))
                or card.find("h2")
            )

            # Company name
            company_el = (
                card.find("span", {"data-testid": "company-name"})
                or card.find("span", class_=re.compile(r"companyName|company", re.I))
                or card.find("a", {"data-testid": "company-name"})
            )

            # Location
            location_el = (
                card.find("div", {"data-testid": "text-location"})
                or card.find("div", class_=re.compile(r"companyLocation|location", re.I))
                or card.find("span", class_=re.compile(r"location", re.I))
            )

            # Salary — validate it contains currency markers before storing
            salary_el = (
                card.find("div", {"data-testid": "attribute_snippet_testid"})
                or card.find("div", class_=re.compile(r"salary|wage", re.I))
                or card.find("span", class_=re.compile(r"salary|wage", re.I))
            )

            # Job URL — prefer organic /rc/clk links; avoid /pagead/ ad trackers
            link_el = (
                card.find("a", {"data-testid": re.compile(r"job|title", re.I)})
                or card.find("a", href=re.compile(r"/rc/clk|/jobs/", re.I))
                or card.find("a", href=re.compile(r"jk=", re.I))
                or card.find("a", href=True)
            )

            if not title_el:
                continue

            title_text = title_el.get_text(strip=True)
            if not title_text:
                continue

            salary_text = ""
            if salary_el:
                raw_salary = salary_el.get_text(strip=True)
                if any(c in raw_salary for c in ["円", "万", "¥", "時給", "月給", "年収"]):
                    salary_text = raw_salary

            job_id = hashlib.md5(
                f"indeed_japan|{title_text}|{location}".encode()
            ).hexdigest()

            raw_href = link_el["href"] if link_el else ""
            full_url = (
                f"https://jp.indeed.com{raw_href}"
                if raw_href and not raw_href.startswith("http")
                else raw_href
            )

            jobs.append(
                {
                    "id": job_id,
                    "source": "indeed_japan",
                    "raw_facility": company_el.get_text(strip=True) if company_el else "",
                    "masked_facility": "",
                    "job_title": title_text,
                    "location": location_el.get_text(strip=True) if location_el else location,
                    # Listing page never has these — detail fetch will populate them
                    "job_description": "",
                    "requirements": "",
                    "salary_raw": salary_text,
                    "salary_masked": "",
                    "employment_type": "",
                    "application_deadline": "",
                    "contact_information": "",
                    "url": full_url,
                    "scraped_at": datetime.utcnow().isoformat(),
                }
            )
    except Exception as e:
        log.error(f"[INDEED] HTML parse error: {e}")

    log.info(f"[INDEED] HTML parsed {len(jobs)} jobs")
    return jobs


# ── Field extraction utilities ────────────────────────────────────────────────

def clean_title(raw: str) -> str:
    if " - " in raw:
        return raw.split(" - ")[0].strip()
    return raw.strip()


def extract_facility(raw: str) -> str:
    if " - " in raw:
        parts = raw.split(" - ")
        return parts[1].strip() if len(parts) > 1 else ""
    return ""


def extract_salary(description: str) -> str:
    if not description:
        return ""
    match = re.search(r"[\d,]+\s*円", description)
    return match.group(0) if match else ""


def strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


async def run() -> list[Job]:
    """Main entry point called by pipeline."""
    all_jobs: list[Job] = []
    for query_config in SEARCH_QUERIES:
        jobs = scrape_indeed_rss(query=query_config["q"], location=query_config["l"])
        all_jobs.extend(jobs)
        log.info(f"[INDEED] Total so far: {len(all_jobs)}")
    return all_jobs
