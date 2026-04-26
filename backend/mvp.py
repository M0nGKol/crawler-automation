from __future__ import annotations

import asyncio

from domain.job import Job
from pipeline import run_pipeline, run_scraper

__all__ = ["Job", "run_scraper"]


if __name__ == "__main__":
    asyncio.run(run_pipeline())
