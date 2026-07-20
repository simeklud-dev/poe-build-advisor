"""Tool-use smyčka: Claude iterativně zkouší úpravy buildu přes reálný PoB engine.

Fáze 2 (viz AI_BUILD_ADVISOR_PLAN.md) -- na rozdíl od fáze 1 (`advisor_llm.py`,
jednorázový komentář), tady Claude dostane nástroje 1:1 namapované na bridge
operace (`advisor_tools.py`) a v cyklu volání/odpověď si sám ověřuje
hypotézy na reálných číslech z PoB enginu, než něco doporučí.
"""

from __future__ import annotations

import json
import logging

from app.advisor_tools import TOOLS, dispatch_tool
from app.config import settings
from app.pob.session import PobSession

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Jsi zkušený Path of Exile theorycrafter s přístupem k reálnému Path of "
    "Building enginu přes nástroje. NIKDY si nevymýšlej čísla ani jména "
    "itemů/modů -- každé tvrzení o DPS/EHP/statu podlož skutečným voláním "
    "nástroje (get_build_summary/get_stat_breakdown), a každý návrh úpravy "
    "před doporučením OVĚŘ pomocí try_item_change/try_node_toggle a porovnej "
    "before/after deltu. Piš česky, stručně a konkrétně -- uveď skutečná "
    "čísla z nástrojů, ne obecné rady. Zkušební úpravy (try_item_change / "
    "try_node_toggle), které nevyšly líp, vrať zpět (zavolej stejný nástroj "
    "znovu s původní hodnotou -- item text zjištěný přes list_equipped_items "
    "PŘED první změnou, node_id znovu pro tree) dřív, než odpovíš, aby "
    "uživateli nezůstal build v rozjetém stavu jen z tvého zkoušení. "
    "Pokud uživatel chce reálné vybavení k nákupu, nejdřív zjisti aktuální "
    "ligu (list_trade_leagues -- jméno ligy se mění každé ~3-4 měsíce, nikdy "
    "nepoužívej jméno z tréninkových dat), pak najdi správné ID statu "
    "(search_trade_stats -- nikdy si ID nevymýšlej) a teprve pak hledej "
    "(search_trade_items). Ceny a nabídky jsou živá data z trade webu, ne "
    "z PoB enginu -- řekni to jasně, když je zmiňuješ."
)

MAX_TOOL_ITERATIONS = 8


class AdvisorChatError(RuntimeError):
    pass


def run_chat_turn(session: PobSession, user_message: str) -> str:
    import anthropic

    if not settings.anthropic_api_key:
        raise AdvisorChatError("ANTHROPIC_API_KEY není nastavený na serveru")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    session.chat_history.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=session.chat_history,
        )
        session.chat_history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = dispatch_tool(session, block.name, block.input)
                content = json.dumps(result, ensure_ascii=False)
                is_error = False
            except Exception as exc:
                logger.exception("advisor tool %s failed", block.name)
                content = str(exc)
                is_error = True
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                }
            )
        session.chat_history.append({"role": "user", "content": tool_results})

    return (
        "Omlouvám se, došel mi počet kroků na ověřování v tomhle tahu -- "
        "zkus prosím pokračovat další zprávou, naváži na to, co už vím."
    )
