from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class AppSettings:
    anthropic_key: str
    sheet_id: str
    creds_path: str
    sites_filter: str
    masking_limit: int
    output_dir: Path
    config_path: Path


def load_settings() -> AppSettings:
    load_dotenv()
    settings = AppSettings(
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", ""),
        sheet_id=os.getenv("SHEET_DEFAULT", os.getenv("GOOGLE_SHEET_ID", "")),
        creds_path=os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS",
            "mvp-scraper-493902-fafa1eb25d83.json",
        ),
        sites_filter=os.getenv("SITES", "all"),
        masking_limit=int(os.getenv("MASKING_LIMIT", "30")),
        output_dir=Path("output"),
        config_path=Path("config/sites.yaml"),
    )
    settings.output_dir.mkdir(exist_ok=True)
    return settings


def load_sites_config(config_path: Path) -> dict[str, Any]:
    with open(config_path, encoding="utf-8") as file:
        loaded = yaml.safe_load(file)
    return loaded["sites"]


def parse_sites_yaml(raw_yaml: str | None) -> dict[str, Any]:
    if not raw_yaml:
        return {}
    loaded = yaml.safe_load(raw_yaml) or {}
    if isinstance(loaded, dict) and isinstance(loaded.get("sites"), dict):
        return loaded["sites"]
    return {}


def merge_sites(default_sites: dict[str, Any], user_sites: dict[str, Any]) -> dict[str, Any]:
    merged = dict(default_sites)
    merged.update(user_sites)
    return merged
