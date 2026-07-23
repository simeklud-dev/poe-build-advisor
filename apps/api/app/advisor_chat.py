"""Tool-use smyčka: Gemini iterativně zkouší úpravy buildu přes reálný PoB engine.

Fáze 2 (viz AI_BUILD_ADVISOR_PLAN.md) -- na rozdíl od fáze 1 (`advisor_llm.py`,
jednorázový komentář), tady model dostane nástroje 1:1 namapované na bridge
operace (`advisor_tools.py`) a v cyklu volání/odpověď si sám ověřuje
hypotézy na reálných číslech z PoB enginu, než něco doporučí.

Poskytovatel: Google Gemini (free tier) -- viz AI_BUILD_ADVISOR_PLAN.md,
sekce o migraci z Anthropic Claude. Google's prompt caching nemá tady
smysl (Gemini free tier nemá cenu za token, kterou by bylo co optimalizovat),
takže se oproti dřívější Claude verzi vypouští, nepřekládá.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from google.genai import errors as genai_errors
from google.genai import types

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
    "z PoB enginu -- řekni to jasně, když je zmiňuješ. Jewely v pasivním "
    "stromě (včetně Timeless Jewelů jako Lethal Pride/Glorious Vanity) "
    "NEJSOU v list_equipped_items -- na cokoliv o nich (jestli je nějaký "
    "socketnutý, jaký, co dělá) použij list_jewels. Timeless Jewel mění "
    "jména/staty blízkých uzlů stromu -- list_passive_tree ti ukáže už "
    "transformované uzly, ale bez list_jewels nebudeš vědět, že a čím "
    "je to způsobené.\n\n"
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

# Brainstorm chat bez nahraného buildu (viz app/free_chat_session.py) -- žádná
# session, žádný bridge, takže žádné PoB-vázané nástroje (get_build_summary,
# try_item_change, ...). Trade nástroje ale fungují nezávisle na buildu
# (dispatch_tool je vyřizuje před tím, než se sáhne na session.bridge), takže
# tenhle mód pořád může doporučit reálné itemy s reálnou cenou -- jen bez
# ověření na skutečném enginu, protože žádný build zatím neexistuje.
FREE_CHAT_SYSTEM_PROMPT = (
    "Jsi zkušený Path of Exile theorycrafter. Uživatel zatím NEMÁ nahraný "
    "žádný build -- pomáháš mu vymyslet koncept od nuly (např. 'chci hrát "
    "skill X, chci hodně damage a rychlý clear, defenzíva mě moc nezajímá'). "
    "Nemáš přístup k PoB enginu ani k žádným reálným statům postavy -- "
    "všechny návrhy jsou z tvých obecných znalostí hry, ne ověřené výpočtem. "
    "Řekni to uživateli jasně, hlavně u konkrétních čísel DPS/EHP (odhad, "
    "ne měření). Piš česky, stručně a konkrétně -- skill, hlavní support "
    "gemy, klíčové unique itemy nebo ascendancy, na co narazí za slabiny. "
    "Máš k dispozici trade nástroje (list_trade_leagues/search_trade_stats/"
    "search_trade_items) na reálné ceny/dostupnost itemů -- nejdřív zjisti "
    "ligu, pak správné ID statu (nikdy si ID nevymýšlej), teprve pak hledej. "
    "Na konci dej uživateli najevo, že jakmile si build sestaví v Path of "
    "Building a vloží export kód do appky, můžeš návrh ověřit na reálném "
    "enginu a doladit."
)

MAX_TOOL_ITERATIONS = 10

# Injected on the second-to-last iteration -- a nudge to wrap up. On its own
# this wasn't enough on a real, fully-built character (many items/gems/tree
# nodes to review): the model judged it genuinely still needed more tool
# calls and kept going anyway, hitting the hard MAX_TOOL_ITERATIONS fallback
# below with nothing to show for it every time. The actual guarantee is
# structural, not a request -- see the last-iteration tools omission below.
WRAP_UP_REMINDER = (
    "\n\nZBÝVÁ TI JEDNO POSLEDNÍ KOLO, KDY MŮŽEŠ POUŽÍT NÁSTROJ. Pokud ještě "
    "potřebuješ ověřit něco zásadního, udělej to přesně teď -- příští "
    "odpověď od tebe už MUSÍ být čistý text bez volání nástrojů (systém ti "
    "žádný nenabídne), takže shrň doporučení na základě toho, co do té doby "
    "budeš vědět."
)


class AdvisorChatError(RuntimeError):
    pass


def _compact_turn_history(
    chat_history: list[dict[str, Any]], history_len_before_turn: int, user_message: str, reply_text: str
) -> None:
    """Collapse a finished turn's tool-call scratch work down to just the
    visible question + final answer before it's carried into the next
    turn's context. Gemini has no server-side prompt caching the way
    Anthropic did -- every generate_content call resends the *entire*
    history verbatim -- so left uncompacted, a session's per-call token
    cost (and therefore how fast it eats the free tier's per-minute TPM
    budget) grows without bound across turns, even though only the
    intermediate function_call/function_response plumbing drove that
    growth, not the answer itself. The final text reply already contains
    whatever the tool calls turned up (item stats, trade links, deltas),
    so the model doesn't lose real information it needs for follow-ups --
    only the scratch work to get there."""
    del chat_history[history_len_before_turn:]
    chat_history.append({"role": "user", "parts": [{"text": user_message}]})
    chat_history.append({"role": "model", "parts": [{"text": reply_text}]})


def _to_gemini_tool(tools: list[dict]) -> types.Tool:
    """TOOLS (advisor_tools.py) is already a plain JSON-schema-shaped list --
    Gemini's FunctionDeclaration takes that schema verbatim via
    parameters_json_schema, so this is a field rename, not a rewrite."""
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters_json_schema=t["input_schema"],
            )
            for t in tools
        ]
    )


GEMINI_TOOL = _to_gemini_tool(TOOLS)

FREE_CHAT_TOOL_NAMES = {"list_trade_leagues", "search_trade_stats", "search_trade_items"}
FREE_CHAT_GEMINI_TOOL = _to_gemini_tool([t for t in TOOLS if t["name"] in FREE_CHAT_TOOL_NAMES])


def _to_plain(value):
    """Recursively convert whatever the Gemini SDK hands back for a
    function_call's `args` (observed as a plain dict in testing, but the
    exact wrapper type is an SDK implementation detail not worth trusting
    blindly -- see AI_BUILD_ADVISOR_PLAN.md verification notes) into plain
    JSON-safe Python types. search_trade_items's stat_filters is a nested
    array-of-objects, so a shallow dict() cast alone isn't enough."""
    if hasattr(value, "items"):
        return {k: _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _run_turn(
    chat_history: list[dict[str, Any]],
    user_message: str,
    *,
    system_prompt: str,
    gemini_tool: types.Tool,
    dispatch: Callable[[str, dict[str, Any]], Any],
) -> str:
    """Shared tool-use loop behind both run_chat_turn (real PoB session) and
    run_free_chat_turn (no build loaded yet, trade tools only) -- the two
    only differ in which tools/system prompt/dispatch function they pass in."""
    from google import genai

    if not settings.gemini_api_key:
        raise AdvisorChatError("GEMINI_API_KEY není nastavený na serveru")

    client = genai.Client(api_key=settings.gemini_api_key)
    # Snapshot so a mid-turn API failure (e.g. quota exhausted after several
    # tool-call rounds) can roll the whole turn back instead of leaving a
    # dangling user message or half-finished tool-call exchange in history
    # for the next request to choke on.
    history_len_before_turn = len(chat_history)
    chat_history.append({"role": "user", "parts": [{"text": user_message}]})

    for iteration in range(MAX_TOOL_ITERATIONS):
        is_last_iteration = iteration == MAX_TOOL_ITERATIONS - 1

        system_text = system_prompt
        if iteration >= MAX_TOOL_ITERATIONS - 2:
            system_text += WRAP_UP_REMINDER

        config = types.GenerateContentConfig(
            system_instruction=system_text,
            # The forced text-only last iteration has to synthesize
            # everything gathered across skills/gear/tree into one answer --
            # measured hitting the 4096 default on a real, fully-built
            # character. Give it real headroom; intermediate tool-use rounds
            # rarely write long prose so 4096 stays plenty for those.
            max_output_tokens=8192 if is_last_iteration else 4096,
            # On a real, fully-built character (many items/gems/tree nodes),
            # WRAP_UP_REMINDER alone wasn't enough -- the model judged it
            # genuinely still needed more tool calls and kept going anyway,
            # exhausting every iteration and hitting the hard fallback below
            # with nothing to show for it. Omitting `tools` entirely on the
            # last iteration makes emitting a function_call structurally
            # impossible, so this loop always ends with a real synthesized
            # answer instead of the empty fallback.
            tools=None if is_last_iteration else [gemini_tool],
        )
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=chat_history,
                config=config,
            )
        except genai_errors.APIError as exc:
            # Roll back so a retry starts clean instead of piling onto a
            # broken turn -- see history_len_before_turn note above.
            del chat_history[history_len_before_turn:]
            if exc.code == 429:
                logger.warning("Gemini free-tier quota/rate limit hit: %s", exc)
                return (
                    "Došel volný limit Gemini API (zdarma tier má omezený počet "
                    "dotazů za den/minutu) -- zkus to prosím za chvíli znovu, "
                    "limit se pravidelně obnovuje."
                )
            logger.exception("Gemini API call failed")
            return "Volání Gemini API selhalo -- zkus to prosím znovu."

        if not response.candidates:
            logger.warning(
                "advisor chat: no candidates in Gemini response (prompt_feedback=%s)",
                getattr(response, "prompt_feedback", None),
            )
            return (
                "Odpověď byla zablokovaná bezpečnostním filtrem -- zkus "
                "prosím otázku přeformulovat."
            )

        candidate = response.candidates[0]
        parts = candidate.content.parts if candidate.content else []

        if candidate.finish_reason == types.FinishReason.MAX_TOKENS:
            if is_last_iteration:
                # No tools were offered on this call, so there's no dangling
                # function_call risk here (that's what the discard-and-
                # generic-message fallback below exists to avoid) -- a
                # truncated answer, even cut off mid-sentence, is still more
                # useful to the user than a "too long, try again" message
                # with nothing in it. Return whatever text made it out.
                text = "".join(p.text for p in parts if p.text)
                if text:
                    _compact_turn_history(chat_history, history_len_before_turn, user_message, text)
                    return text
            logger.warning("advisor chat response truncated at max_tokens, discarding turn")
            return (
                "Odpověď byla příliš dlouhá a musel jsem ji uříznout -- zkus "
                "prosím konkrétnější nebo kratší otázku."
            )

        function_calls = [p.function_call for p in parts if p.function_call]

        chat_history.append(candidate.content.model_dump(exclude_none=True))

        if not function_calls:
            text = "".join(p.text for p in parts if p.text)
            _compact_turn_history(chat_history, history_len_before_turn, user_message, text)
            return text

        response_parts = []
        for call in function_calls:
            try:
                result = dispatch(call.name, _to_plain(call.args))
                payload = {"result": result}
            except Exception as exc:
                logger.exception("advisor tool %s failed", call.name)
                # Gemini's function response has no first-class is_error flag
                # like Anthropic's tool_result -- the "error" key presence is
                # the signal the model reads instead.
                payload = {"error": str(exc)}
            response_parts.append(
                types.Part.from_function_response(name=call.name, response=payload).model_dump(
                    exclude_none=True
                )
            )
        # Gemini rejects role="tool" (400 INVALID_ARGUMENT) despite what the docs
        # implied -- confirmed via live smoke test. Valid roles for this are just
        # user/model; function responses go back as "user", mirroring Anthropic's
        # own convention of using "user" role for tool_result messages.
        chat_history.append({"role": "user", "parts": response_parts})

    # Should be unreachable now that the last iteration omits `tools` (forcing
    # a text response), but kept as a last-resort guard in case the model
    # ever returns no text parts at all on that call.
    return (
        "Omlouvám se, došel mi počet kroků na ověřování v tomhle tahu -- "
        "zkus prosím pokračovat další zprávou, naváži na to, co už vím."
    )


def run_chat_turn(session: PobSession, user_message: str) -> str:
    def dispatch(name: str, tool_input: dict[str, Any]) -> Any:
        result = dispatch_tool(session, name, tool_input)
        if name == "get_build_summary":
            result = curate_summary(result)
        return result

    return _run_turn(
        session.chat_history,
        user_message,
        system_prompt=SYSTEM_PROMPT,
        gemini_tool=GEMINI_TOOL,
        dispatch=dispatch,
    )


def run_free_chat_turn(chat_history: list[dict[str, Any]], user_message: str) -> str:
    """Brainstorm chat with no PoB session -- see FREE_CHAT_SYSTEM_PROMPT.
    Only trade tools are ever offered, and dispatch_tool handles those
    before touching `session.bridge`, so passing None here is safe."""

    def dispatch(name: str, tool_input: dict[str, Any]) -> Any:
        return dispatch_tool(None, name, tool_input)  # type: ignore[arg-type]

    return _run_turn(
        chat_history,
        user_message,
        system_prompt=FREE_CHAT_SYSTEM_PROMPT,
        gemini_tool=FREE_CHAT_GEMINI_TOOL,
        dispatch=dispatch,
    )
