from __future__ import annotations


async def get_text(el, selector: str) -> str:
    if not selector or not el:
        return ""
    try:
        found = await el.query_selector(selector)
        return (await found.inner_text()).strip() if found else ""
    except Exception:
        return ""


async def get_href(el, selector: str) -> str:
    if not selector or not el:
        return ""
    try:
        found = await el.query_selector(selector)
        return await found.get_attribute("href") if found else ""
    except Exception:
        return ""
