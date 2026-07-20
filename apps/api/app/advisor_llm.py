"""Volitelný jednorázový komentář od Claude nad staty buildu spočtenými PoB enginem.

Fáze 1 (viz AI_BUILD_ADVISOR_PLAN.md): žádná tool-use smyčka -- jen jedno
vyhodnocení nad hotovým `get_summary()` výstupem z `app/pob/bridge.py`. Claude
tedy nic nepočítá ani neodhaduje, jen komentuje reálná čísla z enginu. Tool-use
smyčka s co-by-kdyby simulací (try_item_change apod.) přijde ve fázi 2.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Jsi zkušený Path of Exile theorycrafter. Dostaneš JSON se staty buildu "
    "spočtenými enginem Path of Building (jsou to skutečná spočtená čísla, "
    "ne odhad). Ve 2-4 větách česky shrň silné a slabé stránky buildu "
    "(damage, přeživatelnost, resisty) a navrhni, na co se zaměřit dál. "
    "Drž se dat, která dostaneš -- nevymýšlej si čísla ani jména itemů, "
    "která v datech nejsou."
)


def summarize_build(summary: dict[str, Any]) -> str | None:
    """Vrátí krátký komentář, nebo None (chybějící klíč / chyba volání -- endpoint funguje dál i bez toho)."""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(summary, ensure_ascii=False)}],
        )
        return "".join(block.text for block in message.content if block.type == "text") or None
    except Exception:
        logger.exception("Claude commentary call failed; continuing without it")
        return None
