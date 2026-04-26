from __future__ import annotations

from typing import Any

import anthropic


def get_anthropic_client(api_key: str) -> Any:
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)
