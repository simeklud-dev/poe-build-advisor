"""Volitelný jednorázový komentář od AI nad staty buildu spočtenými PoB enginem.

Fáze 1 (viz AI_BUILD_ADVISOR_PLAN.md): žádná tool-use smyčka -- jen jedno
vyhodnocení nad hotovým `get_summary()` výstupem z `app/pob/bridge.py`. Model
tedy nic nepočítá ani neodhaduje, jen komentuje reálná čísla z enginu. Tool-use
smyčka s co-by-kdyby simulací (try_item_change apod.) přijde ve fázi 2.

Poskytovatel: Google Gemini (free tier) -- viz AI_BUILD_ADVISOR_PLAN.md.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.advisor_tools import curate_summary
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
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                {"role": "user", "parts": [{"text": json.dumps(curate_summary(summary), ensure_ascii=False)}]}
            ],
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, max_output_tokens=500),
        )
        parts = response.candidates[0].content.parts if response.candidates and response.candidates[0].content else []
        text = "".join(p.text for p in parts if p.text)
        return text or None
    except Exception:
        logger.exception("Gemini commentary call failed; continuing without it")
        return None
