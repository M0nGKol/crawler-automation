from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from app.config import load_settings, load_sites_config, merge_sites, parse_sites_yaml
from clients.anthropic_client import get_anthropic_client
from database import SessionLocal, User
from output.csv_sink import save_csv
from output.sheets_sink import save_sheets
from scraping.orchestrator import scrape_all
from services.deadline_filter import is_within_deadline
from services.deduplication import deduplicate_jobs
from services.masking import mask_jobs

log = logging.getLogger(__name__)


async def run_pipeline(user_id: str | None = None) -> dict[str, Any]:
    start = time.monotonic()
    settings = load_settings()
    claude = get_anthropic_client(settings.anthropic_key)

    print("\n" + "═" * 60)
    print("  Healthcare Job Crawler — MVP Demo")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 60 + "\n")

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
    sites_attempted = len(sites)
    log.info(
        "Loaded %d sites (%d default + %d custom)",
        sites_attempted,
        len(default_sites),
        len(user_sites),
    )

    jobs = await scrape_all(sites, settings.sites_filter, claude)
    if not jobs:
        return {"count": 0, "csv": None, "sites_attempted": sites_attempted, "sites_succeeded": 0}

    jobs, _removed = deduplicate_jobs(jobs)
    jobs = mask_jobs(jobs, claude=claude, masking_limit=settings.masking_limit)
    jobs = [job for job in jobs if is_within_deadline(job)]

    csv_path = save_csv(jobs, settings.output_dir)
    sheet_url = save_sheets(
        jobs,
        sheet_id=settings.sheet_id,
        creds_path=settings.creds_path,
        user_id=user_id,
    )

    elapsed = time.monotonic() - start
    return {
        "count": len(jobs),
        "csv": str(csv_path),
        "sheet_url": sheet_url,
        "elapsed": elapsed,
        "sites_attempted": sites_attempted,
        "sites_succeeded": sites_attempted,
    }


def run_scraper(user_id: str | None = None) -> dict[str, Any]:
    return asyncio.run(run_pipeline(user_id=user_id))
