from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from playwright.async_api import async_playwright

from domain.job import Job
from scraping.strategies.claude_fallback_scraper import scrape_claude_fallback
from scraping.strategies.css_scraper import scrape_css

log = logging.getLogger(__name__)


async def scrape_all(
    sites_config: dict[str, Any],
    sites_filter: str,
    claude: Any,
) -> list[Job]:
    filter_list = None if sites_filter.strip().lower() == "all" else [s.strip() for s in sites_filter.split(",")]
    all_jobs: list[Job] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--lang=ja-JP"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
        )

        for site_name, config in sites_config.items():
            if filter_list and site_name not in filter_list:
                continue

            log.info("━━ Scraping: %s (%s)", site_name, config.get("mode", "?"))
            page = await ctx.new_page()
            try:
                await page.goto(config["url"], wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(random.uniform(2, 3))

                mode = config.get("mode", "claude_fallback")
                if mode == "css_selectors":
                    jobs = await scrape_css(page, site_name, config, claude)
                else:
                    jobs = await scrape_claude_fallback(page, site_name, config, claude)

                log.info("  ✓ %d listings collected from %s", len(jobs), site_name)
                all_jobs.extend(jobs)
            except Exception as exc:
                log.error("  ✗ Failed %s: %s", site_name, exc)
            finally:
                await page.close()

        await browser.close()

    return all_jobs
