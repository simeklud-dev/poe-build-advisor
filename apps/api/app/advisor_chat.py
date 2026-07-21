"""Tool-use smyčka: Claude iterativně zkouší úpravy buildu přes reálný PoB engine.

Fáze 2 (viz AI_BUILD_ADVISOR_PLAN.md) -- na rozdíl od fáze 1 (`advisor_llm.py`,
jednorázový komentář), tady Claude dostane nástroje 1:1 namapované na bridge
operace (`advisor_tools.py`) a v cyklu volání/odpověď si sám ověřuje
hypotézy na reálných číslech z PoB enginu, než něco doporučí.
"""

from __future__ import annotations

import json
import logging

from app.advisor_tools import TOOLS, curate_summary, dispatch_tool
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
    "z PoB enginu -- řekni to jasně, když je zmiňuješ.\n\n"
    "Buď efektivní s počtem volání nástrojů (máš jich na jeden tah omezené "
    "množství): get_build_summary/get_stat_breakdown v rámci jednoho tahu "
    "zavolej jen jednou, ne opakovaně, pokud jsi mezitím build nezměnil. Na "
    "obecné otázky ('na co se zaměřit', 'jak zlepším přežití/damage') "
    "odpověz přímo z dat, která už máš -- NEZKOUŠEJ postupně víc "
    "hypotetických itemů/uzlů přes try_item_change/try_node_toggle jen "
    "abys ilustroval možnosti. Tyhle nástroje na ověření použij, jen když "
    "doporučuješ KONKRÉTNÍ item nebo uzel (zmíněný uživatelem, nebo nalezený "
    "přes search_trade_items) -- ne k volnému průzkumu variant."
)

MAX_TOOL_ITERATIONS = 8

# Injected only for the last couple of iterations -- a graceful nudge to
# conclude with whatever's already known instead of mechanically hitting the
# MAX_TOOL_ITERATIONS fallback below with nothing to show for it.
WRAP_UP_REMINDER = (
    "\n\nDOŠLA TI TÉMĚŘ VŠECHNA KOLA NA POUŽÍVÁNÍ NÁSTROJŮ v tomhle tahu. "
    "Pokud ještě potřebuješ ověřit něco zásadního, udělej to teď -- jinak "
    "rovnou napiš finální odpověď s doporučením na základě toho, co už víš, "
    "místo dalšího zkoumání."
)


class AdvisorChatError(RuntimeError):
    pass


def run_chat_turn(session: PobSession, user_message: str) -> str:
    import anthropic

    if not settings.anthropic_api_key:
        raise AdvisorChatError("ANTHROPIC_API_KEY není nastavený na serveru")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    session.chat_history.append({"role": "user", "content": user_message})

    for iteration in range(MAX_TOOL_ITERATIONS):
        # Cache-friendly for every normal call (identical text -> cache hit);
        # only the last 2 iterations use a longer, uncached variant so a
        # near-exhausted turn wraps up instead of mechanically running out.
        system_text = SYSTEM_PROMPT
        if iteration >= MAX_TOOL_ITERATIONS - 2:
            system_text += WRAP_UP_REMINDER
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            # SYSTEM_PROMPT + TOOLS are byte-identical on every single call --
            # within one turn's tool loop (up to MAX_TOOL_ITERATIONS calls) and
            # across every turn of every session. Caching them means only the
            # first call in a while pays full price; the rest read this prefix
            # at ~10% cost.
            system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=session.chat_history,
        )

        if response.stop_reason == "max_tokens":
            # Claude got cut off mid-response -- do NOT append this message to
            # chat_history. A truncated turn can end with tool_use blocks that
            # never got a matching tool_result (Claude was cut off before
            # finishing them), and the Anthropic API rejects any *next* call
            # whose history contains such a dangling tool_use -- that would
            # permanently break every future turn in this session, not just
            # this one. Bumping max_tokens to 4096 (from 1500) makes this rare
            # in practice, but the fallback still needs to be safe.
            logger.warning("advisor chat response truncated at max_tokens, discarding turn")
            return (
                "Odpověď byla příliš dlouhá a musel jsem ji uříznout -- zkus "
                "prosím konkrétnější nebo kratší otázku."
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
                if block.name == "get_build_summary":
                    result = curate_summary(result)
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
