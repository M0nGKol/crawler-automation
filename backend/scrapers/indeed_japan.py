import json
import os
import hashlib
import logging
import re
from datetime import datetime
import xml.etree.ElementTree as ET
from typing import Any

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
RSS_LIMIT_PER_QUERY: int = int(os.getenv("INDEED_RSS_LIMIT", "15"))

# How many detail-page fetches to attempt per pipeline run.
# Now defaults to 15 — curl_cffi handles Cloudflare without spending ScraperAPI
# credits, so enrichment is cheap.
MAX_DETAIL_FETCHES: int = int(os.getenv("INDEED_MAX_DETAIL_FETCHES", "15"))

# Circuit breaker: abort enrichment after this many consecutive failures.
ENRICHMENT_FAILURE_CIRCUIT_BREAKER: int = int(os.getenv("INDEED_ENRICHMENT_CIRCUIT", "3"))

# Fields that must be populated for a job to skip the detail-page fetch.
_ENRICHMENT_FIELDS = ("requirements", "employment_type", "application_deadline", "job_description")


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def _fetch_with_curl_cffi(url: str) -> tuple[str | None, int | None]:
    """
    Fetch a URL by impersonating Chrome's TLS fingerprint via curl_cffi.

    Cloudflare checks the TLS handshake and HTTP/2 fingerprint to distinguish
    real browsers from bots. curl_cffi replicates Chrome's exact fingerprint
    at the C library level — no browser process, ~15MB RAM, free to run.

    Returns (html, status_code) on any response, (None, None) on exception.
    Callers must check the status code — a 403 means IP reputation block and
    ScraperAPI (same server IP) will also fail, so don't waste credits retrying.
    """
    try:
        from curl_cffi import requests as cf_requests
        resp = cf_requests.get(
            url,
            impersonate="chrome120",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            timeout=30,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            return resp.text, 200
        log.warning("[INDEED] curl_cffi got status %d for %s", resp.status_code, url[:80])
        return None, resp.status_code
    except ImportError:
        log.warning("[INDEED] curl_cffi not installed — falling back to ScraperAPI")
        return None, None
    except Exception as exc:
        log.warning("[INDEED] curl_cffi fetch failed for %s: %s", url[:80], exc)
        return None, None


def fetch_url(url: str, use_proxy: bool = False, render_js: bool = False) -> requests.Response:
    """Fetch URL directly or via ScraperAPI (used for listing/search pages)."""
    if use_proxy and SCRAPERAPI_KEY:
        log.info("[INDEED] ScraperAPI (render=%s) for: %s", render_js, url[:80])
        return requests.get(
            "http://api.scraperapi.com",
            params={
                "api_key": SCRAPERAPI_KEY,
                "url": url,
                "country_code": "jp",
                "render": "true" if render_js else "false",
            },
            timeout=60,
        )
    log.info("[INDEED] Direct fetch: %s", url[:80])
    return requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RSS reader)"},
        timeout=30,
    )


def _normalize_indeed_url(url: str) -> str:
    """
    Convert any Indeed URL variant to a canonical viewjob URL.
    Returns an empty string for ad-tracker URLs that cannot be enriched.
    """
    if not url:
        return ""
    if not url.startswith("http"):
        url = f"https://jp.indeed.com{url}"

    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)

    if any(seg in parsed.path for seg in ("/pagead/clk", "/pagead/googleclk", "/pagead/")):
        log.debug("[INDEED] Skipping ad-tracker URL: %s", url[:80])
        return ""

    params = parse_qs(parsed.query)
    jk = params.get("jk", [None])[0]
    if jk:
        return f"https://jp.indeed.com/viewjob?jk={jk}"

    return url


def _is_valid_job_page(html: str) -> bool:
    """Return True only if HTML looks like a real Indeed job detail page."""
    if not html or len(html) < 500:
        return False
    if any(marker in html for marker in [
        "challenge-platform", "cf-browser-verification",
        "Just a moment", "Checking your browser",
        "Enable JavaScript", "cf_chl_",
    ]):
        return False
    return any(marker in html for marker in [
        "jobDescriptionText", "jobsearch-JobComponent",
        "viewJobSSRRoot", "jobDescription",
        "icl-u-xs", "雇用形態", "給与", "勤務地",
    ])


# ── Claude extraction ─────────────────────────────────────────────────────────

def _trim_html(html: str, max_chars: int = 20_000) -> str:
    """Strip navigation/footer noise before sending to Claude."""
    body = html
    for tag in ("script", "style", "nav", "footer", "header", "head"):
        body = re.sub(rf"<{tag}[\s>].*?</{tag}>", "", body, flags=re.DOTALL | re.IGNORECASE)
    for pattern in (
        r"<main[\s>].*?</main>",
        r"<article[\s>].*?</article>",
        r'<div[^>]+(?:id|class)=["\'][^"\']*(?:content|detail|job)[^"\']*["\'][^>]*>.*?</div>',
    ):
        match = re.search(pattern, body, re.DOTALL | re.IGNORECASE)
        if match and len(match.group(0)) > 500:
            return match.group(0)[:max_chars]
    return body[:max_chars]


def _extract_with_claude(html: str, job: Job, claude: Any) -> dict:
    """
    Send trimmed HTML to Claude Haiku and extract all structured job fields.
    Same pattern used by detail_enricher.py for other sites.
    """
    body = _trim_html(html)
    log.info("[INDEED] Sending %d chars to Claude for extraction", len(body))

    try:
        response = claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            system=(
                "You extract structured data from Japanese job detail pages. "
                "Return ONLY a JSON object — no markdown fences, no commentary. "
                "Use the exact field names below. Use empty string for any field you cannot find. "
                "Quote text verbatim from the page when possible.\n\n"
                "Fields:\n"
                '  "raw_facility": company or hospital name\n'
                '  "location": full work address or area\n'
                '  "job_description": role description verbatim (仕事内容)\n'
                '  "requirements": qualifications needed (応募資格, 必要資格)\n'
                '  "salary_raw": salary text verbatim (給与, 月給, 時給, 年収)\n'
                '  "employment_type": 正社員 / パート / 契約社員 / etc (雇用形態)\n'
                '  "application_deadline": deadline (応募期限, 締切)\n'
                '  "contact_information": phone, email, or contact name (連絡先)\n'
            ),
            messages=[{
                "role": "user",
                "content": f"URL: {job.url}\n\nHTML:\n{body}",
            }],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        return {k: str(v or "").strip() for k, v in data.items() if isinstance(data, dict)}
    except json.JSONDecodeError as exc:
        log.warning("[INDEED] Claude JSON parse failed: %s", exc)
        return {}
    except Exception as exc:
        log.warning("[INDEED] Claude extraction failed: %s", exc)
        return {}


# ── Two-pass detail enrichment ────────────────────────────────────────────────

def _needs_enrichment(job: Job) -> bool:
    return any(not getattr(job, field, "") for field in _ENRICHMENT_FIELDS)


def _enrich_jobs(jobs: list[Job], claude: Any = None) -> list[Job]:
    """
    Pass 2: visit each job's detail page to fill empty fields.

    Fetch priority (cheapest first):
      1. curl_cffi Chrome impersonation — free, bypasses Cloudflare TLS check
      2. ScraperAPI render=false        — 1 credit, fallback if curl_cffi fails
      3. ScraperAPI render=true         — 5-10 credits, last resort

    Extraction: Claude Haiku if available, else BeautifulSoup/regex fallback.
    """
    if MAX_DETAIL_FETCHES == 0:
        log.info("[INDEED] Enrichment disabled (INDEED_MAX_DETAIL_FETCHES=0)")
        return jobs

    needs = [j for j in jobs if _needs_enrichment(j)]
    complete = len(jobs) - len(needs)
    to_fetch = needs[:MAX_DETAIL_FETCHES]
    capped = len(needs) - len(to_fetch)

    log.info(
        "[INDEED] Enrichment: %d detail fetches (+%d complete, +%d capped)",
        len(to_fetch), complete, capped,
    )

    consecutive_failures = 0
    fetched = 0
    for job in to_fetch:
        ok = _enrich_job_from_detail(job, claude=claude)
        fetched += 1
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= ENRICHMENT_FAILURE_CIRCUIT_BREAKER:
                log.error(
                    "[INDEED] Circuit breaker tripped after %d consecutive failures — "
                    "aborting enrichment (saved %d further attempts)",
                    consecutive_failures, len(to_fetch) - fetched,
                )
                break

    log.info("[INDEED] Enrichment complete: %d attempts", fetched)
    return jobs


def _enrich_job_from_detail(job: Job, claude: Any = None) -> bool:
    """
    Fetch the job detail page and fill missing fields. Mutates job in-place.

    Returns True if any data was extracted or URL was skippable (for circuit
    breaker logic — only persistent fetch failures count as a failure).
    """
    if not job.url:
        return False

    canonical_url = _normalize_indeed_url(job.url)
    if not canonical_url:
        log.info("[INDEED] Skipping ad-tracker URL: %s", job.url[:80])
        return True  # not a failure — just unenrichable
    if canonical_url != job.url:
        log.info("[INDEED] URL normalized: %s → %s", job.url[:60], canonical_url[:60])
        job.url = canonical_url

    html: str = ""

    # ── Attempt 1: curl_cffi Chrome impersonation (free) ─────────────────────
    fetched_html, curl_status = _fetch_with_curl_cffi(canonical_url)
    if fetched_html and _is_valid_job_page(fetched_html):
        html = fetched_html
        log.info("[INDEED] Detail OK via curl_cffi: %s", canonical_url[:60])
    elif curl_status == 403:
        # 403 = Cloudflare IP reputation block on our server's IP address.
        # curl_cffi fixes TLS fingerprinting but cannot change IP reputation.
        # ScraperAPI standard tier runs on the same datacenter IP range and
        # will hit the same 403 — skip it entirely to avoid burning credits.
        log.warning("[INDEED] IP blocked by Cloudflare (403) — skipping ScraperAPI, saving credits: %s", canonical_url[:60])
        return False
    else:
        # ── Attempt 2: ScraperAPI render=false (1 credit) ────────────────────
        if SCRAPERAPI_KEY:
            try:
                resp = fetch_url(canonical_url, use_proxy=True, render_js=False)
                if resp.status_code == 200 and _is_valid_job_page(resp.text):
                    html = resp.text
                    log.info("[INDEED] Detail OK via ScraperAPI render=false: %s", canonical_url[:60])
                else:
                    # ── Attempt 3: ScraperAPI render=true (5-10 credits) ─────
                    log.info("[INDEED] render=false invalid — upgrading to render=true")
                    resp2 = fetch_url(canonical_url, use_proxy=True, render_js=True)
                    if resp2.status_code == 200 and _is_valid_job_page(resp2.text):
                        html = resp2.text
                        log.info("[INDEED] Detail OK via ScraperAPI render=true: %s", canonical_url[:60])
                    else:
                        log.warning("[INDEED] All fetch attempts failed for: %s", canonical_url[:60])
                        return False
            except Exception as exc:
                log.warning("[INDEED] ScraperAPI fetch failed for %s: %s", canonical_url[:60], exc)
                return False
        else:
            log.warning("[INDEED] curl_cffi failed and no SCRAPERAPI_KEY — skipping: %s", canonical_url[:60])
            return False

    # ── Extraction: Claude (preferred) or BeautifulSoup/regex fallback ────────
    if claude:
        extracted = _extract_with_claude(html, job, claude)
        if extracted:
            _fill_fields(job, extracted)
            filled = [f for f in _ENRICHMENT_FIELDS if getattr(job, f, "")]
            log.info("[INDEED] Claude enriched %r — filled: %s", job.job_title[:40], filled)
            return True

    # Fallback to original regex/BeautifulSoup extraction
    extracted = _extract_detail_fields(html)
    _fill_fields(job, extracted)
    filled = [f for f in _ENRICHMENT_FIELDS if getattr(job, f, "")]
    log.info("[INDEED] BS/regex enriched %r — filled: %s", job.job_title[:40], filled)
    return True


def _fill_fields(job: Job, extracted: dict) -> None:
    """Copy extracted values into job fields — only overwrites empty fields."""
    field_map = {
        "job_description": "job_description",
        "requirements": "requirements",
        "salary_raw": "salary_raw",
        "employment_type": "employment_type",
        "application_deadline": "application_deadline",
        "contact_information": "contact_information",
        "raw_facility": "raw_facility",
    }
    for src, dst in field_map.items():
        value = extracted.get(src, "")
        if value and not getattr(job, dst, ""):
            setattr(job, dst, value)


# ── BeautifulSoup / regex extraction (fallback when Claude unavailable) ───────

def _extract_from_json_ld(soup) -> dict:
    """Extract job fields from JSON-LD structured data embedded in the page."""
    result: dict = {
        "job_description": "", "requirements": "", "employment_type": "",
        "application_deadline": "", "contact_information": "", "salary_raw": "",
    }
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") not in ("JobPosting", "jobPosting"):
                continue
            if item.get("description") and not result["job_description"]:
                desc = re.sub(r"<[^>]+>", " ", str(item["description"]))
                result["job_description"] = desc.strip()[:2000]
            _ET_MAP = {
                "FULL_TIME": "正社員", "PART_TIME": "パート・アルバイト",
                "CONTRACTOR": "契約社員", "TEMPORARY": "派遣社員",
                "INTERN": "インターン", "OTHER": "その他",
            }
            et = item.get("employmentType", "")
            if et and not result["employment_type"]:
                result["employment_type"] = _ET_MAP.get(et.upper(), et)
            if item.get("validThrough") and not result["application_deadline"]:
                result["application_deadline"] = str(item["validThrough"])[:20]
            base = item.get("baseSalary", {})
            if base and not result["salary_raw"]:
                val = base.get("value", {})
                if isinstance(val, dict):
                    mn = val.get("minValue", "")
                    mx = val.get("maxValue", "")
                    unit_map = {"HOUR": "時給", "DAY": "日給", "WEEK": "週給", "MONTH": "月給", "YEAR": "年収"}
                    unit = unit_map.get(str(val.get("unitText", "")).upper(), "")
                    if mn and mx:
                        result["salary_raw"] = f"{unit}{mn}〜{mx}円"
                    elif mn or mx:
                        result["salary_raw"] = f"{unit}{mn or mx}円"
            org = item.get("hiringOrganization", {})
            if isinstance(org, dict) and not result["contact_information"]:
                parts = [p for p in [org.get("name", ""), org.get("telephone", ""), org.get("email", "")] if p]
                if parts:
                    result["contact_information"] = " / ".join(parts)[:200]
            return result
    return result


def _extract_detail_fields(html: str) -> dict:
    """Parse an Indeed Japan detail page with BeautifulSoup + regex (Claude fallback)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_from_json_ld(soup)

    if all(result.get(f) for f in ("job_description", "employment_type")):
        return result

    desc_el = (
        soup.find("div", id="jobDescriptionText")
        or soup.find("div", attrs={"data-testid": "jobsearch-JobComponent-description"})
        or soup.find("div", class_=re.compile(r"jobDescription|jobsearch-jobDescriptionText", re.I))
    )
    if desc_el:
        result["job_description"] = desc_el.get_text(separator="\n", strip=True)[:2000]

    salary_candidates = (
        soup.find_all(attrs={"data-testid": "attribute_snippet_testid"})
        + soup.find_all("div", class_=re.compile(r"salary|wage", re.I))
    )
    for el in salary_candidates:
        text = el.get_text(strip=True)
        if any(c in text for c in ["円", "万", "¥", "時給", "月給", "年収"]):
            result["salary_raw"] = text[:200]
            break

    full_text = soup.get_text(separator="\n")

    employment_el = soup.find(string=re.compile(r"雇用形態|勤務形態"))
    if employment_el:
        parent = employment_el.find_parent()
        sibling = parent.find_next_sibling() if parent else None
        if sibling:
            result["employment_type"] = sibling.get_text(strip=True)[:100]
    if not result["employment_type"]:
        for keyword in ["正社員", "パート", "アルバイト", "契約社員", "派遣社員", "業務委託", "非常勤"]:
            if keyword in full_text:
                result["employment_type"] = keyword
                break

    for pattern in [
        r"応募締切[^\n：:]*[:：]?\s*([^\n]+)",
        r"締切[^\n：:]*[:：]?\s*(\d{4}[年/\-]\d{1,2}[月/\-]\d{1,2})",
        r"(\d{4}年\d{1,2}月\d{1,2}日).*?まで",
    ]:
        match = re.search(pattern, full_text)
        if match:
            result["application_deadline"] = (match.group(1) if match.lastindex else match.group(0)).strip()[:100]
            break

    for pattern in [
        r"(採用担当[^\n]{0,100})", r"(TEL[^\n]{0,80})",
        r"(電話[^\n：:]*[:：]?\s*[\d\-（）()]+)", r"([\w.+-]+@[\w\-]+\.[a-z]{2,})",
    ]:
        match = re.search(pattern, full_text)
        if match:
            result["contact_information"] = match.group(1).strip()[:200]
            break

    req_el = soup.find(string=re.compile(r"応募資格|必要資格|応募条件"))
    if req_el:
        parent = req_el.find_parent()
        block = parent.find_next_sibling() if parent else None
        if block:
            result["requirements"] = block.get_text(separator="\n", strip=True)[:500]

    return result


# ── Domain model conversion ───────────────────────────────────────────────────

def _dict_jobs_to_domain_jobs(job_dicts: list[dict]) -> list[Job]:
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
        job.id = str(jd.get("id", job.id))
        scraped_at = jd.get("scraped_at") or None
        if scraped_at:
            job.scraped_at = str(scraped_at)
        jobs.append(job)
    return jobs


# ── Main scrape entry points ──────────────────────────────────────────────────

def scrape_indeed_rss(query: str, location: str, claude: Any = None) -> list[Job]:
    """
    Pass 1: RSS feed for job discovery.
    Pass 2: curl_cffi + Claude enrichment for detail fields.
    """
    rss_url = f"https://jp.indeed.com/rss?q={query}&l={location}&limit={RSS_LIMIT_PER_QUERY}"

    try:
        response = fetch_url(rss_url, use_proxy=False)
        if response.status_code == 200 and "<rss" in response.text:
            jobs = _dict_jobs_to_domain_jobs(parse_rss(response.text, query, location))
            return _enrich_jobs(jobs, claude=claude)
        log.warning("[INDEED] RSS blocked for %s/%s — trying ScraperAPI", query, location)
    except Exception as e:
        log.warning("[INDEED] RSS failed: %s", e)

    try:
        search_url = f"https://jp.indeed.com/jobs?q={query}&l={location}&limit=50"
        response = fetch_url(search_url, use_proxy=True)
        if response.status_code == 200:
            jobs = _dict_jobs_to_domain_jobs(parse_html(response.text, query, location))
            return _enrich_jobs(jobs, claude=claude)
        log.error("[INDEED] ScraperAPI also failed: %d", response.status_code)
    except Exception as e:
        log.error("[INDEED] ScraperAPI failed: %s", e)

    return []


def _extract_rss_employment_type(desc_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", desc_html)
    for keyword in ["正社員", "パート", "アルバイト", "契約社員", "派遣社員", "業務委託", "非常勤", "嘱託"]:
        if keyword in text:
            return keyword
    return ""


def parse_rss(xml_text: str, query: str, location: str) -> list[dict]:
    """Parse Indeed RSS feed into standard job schema."""
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
            jobs.append({
                "id": job_id,
                "source": "indeed_japan",
                "raw_facility": extract_facility(title.text or ""),
                "masked_facility": "",
                "job_title": clean_title(title.text or ""),
                "location": location,
                "job_description": desc_text[:500],
                "requirements": "",
                "salary_raw": extract_salary(desc_html),
                "salary_masked": "",
                "employment_type": _extract_rss_employment_type(desc_html),
                "application_deadline": "",
                "contact_information": "",
                "url": link.text or "",
                "scraped_at": datetime.utcnow().isoformat(),
            })
    except ET.ParseError as e:
        log.error("[INDEED] RSS parse error: %s", e)
    log.info("[INDEED] RSS parsed %d jobs for %s/%s", len(jobs), query, location)
    return jobs


def parse_html(html: str, query: str, location: str) -> list[dict]:
    """Parse Indeed HTML search results via BeautifulSoup."""
    from bs4 import BeautifulSoup
    jobs: list[dict] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        job_cards = (
            soup.find_all("div", class_="job_seen_beacon")
            or soup.find_all("div", {"data-testid": "slider_item"})
            or soup.find_all("li", class_=re.compile(r"job", re.I))
            or soup.find_all("div", class_=re.compile(r"jobCard|job-card|resultContent", re.I))
        )
        log.info("[INDEED] Found %d job cards in HTML", len(job_cards))
        for card in job_cards:
            title_el = (
                card.find("span", {"data-testid": "jobTitle"})
                or card.find("span", id=re.compile(r"jobTitle", re.I))
                or card.find("h2", class_=re.compile(r"jobTitle|job-title", re.I))
                or card.find("h2")
            )
            company_el = (
                card.find("span", {"data-testid": "company-name"})
                or card.find("span", class_=re.compile(r"companyName|company", re.I))
            )
            location_el = (
                card.find("div", {"data-testid": "text-location"})
                or card.find("div", class_=re.compile(r"companyLocation|location", re.I))
            )
            salary_el = (
                card.find("div", {"data-testid": "attribute_snippet_testid"})
                or card.find("div", class_=re.compile(r"salary|wage", re.I))
            )
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
            job_id = hashlib.md5(f"indeed_japan|{title_text}|{location}".encode()).hexdigest()
            raw_href = link_el["href"] if link_el else ""
            full_url = (
                f"https://jp.indeed.com{raw_href}"
                if raw_href and not raw_href.startswith("http")
                else raw_href
            )
            jobs.append({
                "id": job_id,
                "source": "indeed_japan",
                "raw_facility": company_el.get_text(strip=True) if company_el else "",
                "masked_facility": "",
                "job_title": title_text,
                "location": location_el.get_text(strip=True) if location_el else location,
                "job_description": "",
                "requirements": "",
                "salary_raw": salary_text,
                "salary_masked": "",
                "employment_type": "",
                "application_deadline": "",
                "contact_information": "",
                "url": full_url,
                "scraped_at": datetime.utcnow().isoformat(),
            })
    except Exception as e:
        log.error("[INDEED] HTML parse error: %s", e)
    log.info("[INDEED] HTML parsed %d jobs", len(jobs))
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


async def run(claude: Any = None) -> list[Job]:
    """Main entry point called by pipeline. Accepts claude client for enrichment."""
    all_jobs: list[Job] = []
    for query_config in SEARCH_QUERIES:
        jobs = scrape_indeed_rss(
            query=query_config["q"],
            location=query_config["l"],
            claude=claude,
        )
        all_jobs.extend(jobs)
        log.info("[INDEED] Total so far: %d", len(all_jobs))
    return all_jobs
