"""
Main scraping pipeline.

Responsibilities:
  1. Load site config (default + user-overrides).
  2. Scrape each site via safe_scrape() — failing scrapers never crash the pipeline.
  3. Deduplicate across current and previous runs using MD5 hashes.
  4. Apply deadline filter.
  5. Mask sensitive fields (facility + salary) via Claude or rule-based fallback.
  6. Split into JobRaw and JobMasked lists (same id for cross-reference).
  7. Write to CSV (raw_data.csv + masked_data.csv).
  8. Write to Google Sheets (raw_data tab + masked_data tab).
  9. Update scraper_sites.last_status in the DB.
  10. Return a rich result dict for the run log.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import load_settings, load_sites_config, merge_sites, parse_sites_yaml
from clients.anthropic_client import get_anthropic_client
from database import ScraperSite, SessionLocal, User
from models import JobMasked, JobRaw
from output.csv_sink import save_csv
from output.sheets_sink import write_to_sheets
from scraping.orchestrator import scrape_all
from services.deadline_filter import is_within_deadline
from services.deduplication import deduplicate_jobs
from services.masking import mask_jobs

log = logging.getLogger(__name__)

BLOCKED_SITE_REPORTS: dict[str, dict[str, str]] = {
    "indeed_japan": {
        "status": "skipped",
        "reason": "cloudflare_blocked",
        "log_message": "indeed_japan skipped: Cloudflare protected, no viable free endpoint",
    }
}


# ── TASK 6: Safe per-scraper wrapper ────────────────────────────────────────

async def safe_scrape(scraper_coro: Any, site_name: str) -> list:
    """
    Await a scraper coroutine. On any exception, log the error and return [].
    A failing scraper must NEVER crash the whole pipeline.
    """
    try:
        return await scraper_coro
    except Exception as exc:
        log.error("[%s] scraper failed: %s", site_name, exc)
        return []


# ── TASK 7: Site seeding ─────────────────────────────────────────────────────

def _seed_scraper_sites(sites_config: dict[str, Any]) -> None:
    """Insert default sites into scraper_sites table if they don't exist yet."""
    db = SessionLocal()
    try:
        for site_name, cfg in sites_config.items():
            existing = (
                db.query(ScraperSite)
                .filter(ScraperSite.site_name == site_name)
                .first()
            )
            if not existing:
                site = ScraperSite(
                    id=uuid.uuid4().hex,
                    site_name=site_name,
                    url=cfg.get("url", ""),
                    is_default=True,
                    is_active=cfg.get("active", True),
                    last_status="unknown",
                )
                db.add(site)
        db.commit()
    except Exception as exc:
        log.error("Failed to seed scraper_sites: %s", exc)
        db.rollback()
    finally:
        db.close()


def _update_site_status(site_name: str, status: str) -> None:
    """Update last_status and last_run_at for a site in scraper_sites."""
    db = SessionLocal()
    try:
        site = (
            db.query(ScraperSite)
            .filter(ScraperSite.site_name == site_name)
            .first()
        )
        if site:
            site.last_status = status
            site.last_run_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        log.error("Failed to update site status for %s: %s", site_name, exc)
        db.rollback()
    finally:
        db.close()


# ── TASK 5: Build JobRaw / JobMasked from masked Job objects ─────────────────

def _build_output_models(
    jobs: list,  # list[Job] after masking
) -> tuple[list[JobRaw], list[JobMasked]]:
    """
    Convert internal Job objects into JobRaw and JobMasked output dataclasses.
    Each pair shares the same id so raw ↔ masked rows can be cross-referenced.
    """
    jobs_raw: list[JobRaw] = []
    jobs_masked: list[JobMasked] = []

    for job in jobs:
        job_id = getattr(job, "id", uuid.uuid4().hex[:10])
        scraped_at = getattr(job, "scraped_at", datetime.utcnow().isoformat())

        jobs_raw.append(
            JobRaw(
                id=job_id,
                source=getattr(job, "source", ""),
                facility=getattr(job, "raw_facility", ""),
                job_title=getattr(job, "job_title", ""),
                location=getattr(job, "location", ""),
                job_description=getattr(job, "job_description", ""),
                requirements=getattr(job, "requirements", ""),
                salary=getattr(job, "salary_raw", ""),
                employment_type=getattr(job, "employment_type", ""),
                application_deadline=getattr(job, "application_deadline", ""),
                contact_information=getattr(job, "contact_information", ""),
                url=getattr(job, "url", ""),
                scraped_at=scraped_at,
            )
        )
        jobs_masked.append(
            JobMasked(
                id=job_id,
                source=getattr(job, "source", ""),
                facility=getattr(job, "masked_facility", "") or "●●●",
                job_title=getattr(job, "job_title", ""),
                location=getattr(job, "location", ""),
                job_description=getattr(job, "job_description", ""),
                requirements=getattr(job, "requirements", ""),
                salary=getattr(job, "salary_masked", "") or "●●●",
                employment_type=getattr(job, "employment_type", ""),
                application_deadline=getattr(job, "application_deadline", ""),
                contact_information=getattr(job, "contact_information", ""),
                url=getattr(job, "url", ""),
                scraped_at=scraped_at,
            )
        )

    return jobs_raw, jobs_masked


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_pipeline(
    user_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    start = time.monotonic()
    settings = load_settings()
    claude = get_anthropic_client(settings.anthropic_key)

    print("\n" + "═" * 60)
    print("  Healthcare Job Crawler — Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 60 + "\n")

    # Load site config
    default_sites = load_sites_config(settings.config_path)
    user_sites: dict[str, Any] = {}
    if user_id:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user_sites = parse_sites_yaml(user.sites_config)
        finally:
            db.close()

    sites = merge_sites(default_sites, user_sites)

    # Seed default sites into DB (Task 7)
    _seed_scraper_sites(default_sites)

    # Filter to only active sites from config and DB, logging skips without
    # treating them as scraper failures.
    db_active_map: dict[str, bool] = {}
    db = SessionLocal()
    try:
        rows = db.query(ScraperSite.site_name, ScraperSite.is_active).all()
        db_active_map = {row.site_name: bool(row.is_active) for row in rows}
    except Exception:
        pass
    finally:
        db.close()

    active_sites: dict[str, Any] = {}
    site_reports: dict[str, dict[str, str]] = {}
    for site_name, cfg in sites.items():
        blocked_report = BLOCKED_SITE_REPORTS.get(site_name)
        if blocked_report:
            log.info(blocked_report["log_message"])
            site_reports[site_name] = {
                "status": blocked_report["status"],
                "reason": blocked_report["reason"],
            }
            _update_site_status(site_name, blocked_report["status"])
            continue

        if cfg.get("active", True) is False:
            log.info("Skipping %s: marked inactive", site_name)
            site_reports[site_name] = {"status": "skipped", "reason": "inactive"}
            _update_site_status(site_name, "skipped")
            continue

        if site_name in db_active_map and db_active_map[site_name] is False:
            log.info("Skipping %s: marked inactive", site_name)
            site_reports[site_name] = {"status": "skipped", "reason": "inactive"}
            _update_site_status(site_name, "skipped")
            continue

        active_sites[site_name] = cfg

    sites = active_sites

    sites_attempted = len(sites)
    log.info(
        "Running %d active sites (%d default + %d custom, %d skipped inactive)",
        sites_attempted,
        len(default_sites),
        len(user_sites),
        len(site_reports),
    )

    # Scrape all sites with per-site isolation (Task 6)
    # The orchestrator already handles per-site errors; we track status here
    jobs = await scrape_all(sites, settings.sites_filter, claude)

    # Update site statuses (best-effort: mark attempted as succeeded for now;
    # the orchestrator already logs individual failures)
    sites_succeeded = 0
    sites_failed = 0
    for site_name in sites:
        # Heuristic: if any jobs came from this site, mark success
        site_jobs = [j for j in jobs if getattr(j, "source", "") == site_name]
        if site_jobs:
            _update_site_status(site_name, "success")
            sites_succeeded += 1
            site_reports[site_name] = {"status": "success"}
        else:
            _update_site_status(site_name, "failed")
            sites_failed += 1
            site_reports[site_name] = {"status": "failed"}

    if not jobs:
        return {
            "count": 0,
            "jobs_raw": 0,
            "jobs_masked": 0,
            "csv_raw": None,
            "csv_masked": None,
            "sheet_url": None,
            "elapsed": time.monotonic() - start,
            "sites_attempted": sites_attempted,
            "sites_succeeded": sites_succeeded,
            "sites_failed": sites_failed,
            "site_reports": site_reports,
        }

    # Dedup (in-run + cross-run via DB)
    jobs, _removed = deduplicate_jobs(jobs)
    log.info(f"[PIPELINE] After dedup: {len(jobs)} jobs")

    # Deadline filter
    jobs = [job for job in jobs if is_within_deadline(job)]
    log.info(f"[PIPELINE] After deadline filter: {len(jobs)} jobs")

    # Mask sensitive fields
    jobs = mask_jobs(jobs, claude=claude, masking_limit=settings.masking_limit)
    log.info(f"[PIPELINE] After masking: {len(jobs)} jobs")

    # Build output models (Task 5)
    jobs_raw, jobs_masked = _build_output_models(jobs)
    log.info(f"[PIPELINE] After model build: {len(jobs_raw)} raw, {len(jobs_masked)} masked")

    # Write CSV (Task 4)
    raw_csv, masked_csv = save_csv(jobs_raw, jobs_masked, str(settings.output_dir))

    # Write Sheets (Task 3)
    log.info(f"[PIPELINE] Calling write_to_sheets with user_id: {user_id}")
    try:
        sheet_url = write_to_sheets(
            jobs_raw,
            jobs_masked,
            sheet_id=settings.sheet_id,
            creds_path=settings.creds_path,
            user_id=user_id,
        )
        log.info(f"[PIPELINE] Sheets write completed, url: {sheet_url}")
    except Exception as e:
        log.error(f"[PIPELINE] write_to_sheets failed: {e}", exc_info=True)
        sheet_url = None

    elapsed = time.monotonic() - start
    return {
        "count": len(jobs),
        "jobs_raw": len(jobs_raw),
        "jobs_masked": len(jobs_masked),
        "csv": str(raw_csv),
        "csv_raw": str(raw_csv),
        "csv_masked": str(masked_csv),
        "sheet_url": sheet_url,
        "elapsed": elapsed,
        "sites_attempted": sites_attempted,
        "sites_succeeded": sites_succeeded,
        "sites_failed": sites_failed,
        "site_reports": site_reports,
    }


def run_scraper(user_id: str | None = None) -> dict[str, Any]:
    return asyncio.run(run_pipeline(user_id=user_id))
