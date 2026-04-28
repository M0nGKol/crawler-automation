from __future__ import annotations

from typing import Any

import httpx


async def fetch_json_api(url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    timeout = httpx.Timeout(30.0, connect=10.0)
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True, http2=True) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("jobs", "items", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []
