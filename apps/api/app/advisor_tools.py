"""Nástroje (tools) pro Claude nad co-by-kdyby operacemi bridge (fáze 2).

Každý nástroj je tenký obal nad `PobBridge.call(...)` (viz
`app/pob/bridge.py`, `apps/api/lua/pob-bridge.lua`) -- Claude nikdy nepočítá
čísla sám, jen volá tyhle nástroje a reaguje na reálný výsledek z PoB enginu.
"""

from __future__ import annotations

from typing import Any

from app.pob.decode import encode_pob_code
from app.pob.session import PobSession

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_build_summary",
        "description": "Vrátí aktuální spočtené staty buildu (DPS, life, energy shield, resisty, EHP, ...) z reálného PoB enginu.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_stat_breakdown",
        "description": (
            "Vrátí formulí-anotovaný rozklad výpočtu konkrétního statu přesně "
            "tak, jak ho PoB ukazuje v Calcs tabu -- použij, když je potřeba "
            "vysvětlit PROČ má stat danou hodnotu."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "stat": {
                    "type": "string",
                    "description": "Přesné jméno statu, např. 'CritChance', 'TotalDPS', 'PhysicalMaximumHitTaken'.",
                }
            },
            "required": ["stat"],
        },
    },
    {
        "name": "list_equipped_items",
        "description": "Vrátí aktuálně nasazené itemy po slotech (název slotu -> syrový text itemu).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "try_item_change",
        "description": (
            "Nasadí item (syrový text přesně ve formátu z in-game kopie / PoB) "
            "do zadaného slotu a přepočítá build. ZMĚNA ZŮSTÁVÁ (není to jen "
            "náhled) -- pokud výsledek není lepší, vrať ji zpět dalším "
            "voláním s původním textem itemu (zjisti ho přes "
            "list_equipped_items PŘED první změnou)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "slot": {
                    "type": "string",
                    "description": "Přesný název slotu z list_equipped_items, např. 'Weapon 1', 'Body Armour', 'Boots'.",
                },
                "item_text": {
                    "type": "string",
                    "description": "Syrový text itemu (Rarity: .../Item Level: .../řádky modů...).",
                },
            },
            "required": ["slot", "item_text"],
        },
    },
    {
        "name": "try_node_toggle",
        "description": (
            "Přepne alokaci uzlu na pasivním stromu (alokuje, pokud není "
            "alokovaný, jinak deallokuje) a přepočítá build. POZOR: alokace "
            "vzdáleného uzlu automaticky přialokuje i propojovací cestu (víc "
            "uzlů najednou, víc bodů); deallokace odebere jen uzly, které by "
            "se staly nedosažitelnými -- cestovní uzly potřebné jinde mohou "
            "zůstat alokované, přesně jako shift-click v reálném PoB stromu."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"node_id": {"type": "integer", "description": "ID uzlu na pasivním stromu."}},
            "required": ["node_id"],
        },
    },
    {
        "name": "export_build",
        "description": "Vygeneruje aktuální (upravený) build jako PoB export kód pro re-import do desktop Path of Building.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def compute_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Vrátí jen staty, které se změnily -- posílat Claude celý 630polí dump
    před/po by zbytečně žral kontext, delta je to, co ho zajímá."""
    delta: dict[str, Any] = {}
    for key in set(before) | set(after):
        b, a = before.get(key), after.get(key)
        if b != a:
            entry: dict[str, Any] = {"before": b, "after": a}
            if isinstance(b, (int, float)) and isinstance(a, (int, float)):
                entry["change"] = a - b
            delta[key] = entry
    return delta


def dispatch_tool(session: PobSession, name: str, tool_input: dict[str, Any]) -> Any:
    bridge = session.bridge
    if name == "get_build_summary":
        return bridge.call("get_summary")
    if name == "get_stat_breakdown":
        return bridge.call("get_breakdown", {"stat": tool_input["stat"]})
    if name == "list_equipped_items":
        return bridge.call("list_items")
    if name == "try_item_change":
        result = bridge.call("try_item_change", {"slot": tool_input["slot"], "item_text": tool_input["item_text"]})
        return {"slot": result["slot"], "delta": compute_delta(result["before"], result["after"])}
    if name == "try_node_toggle":
        result = bridge.call("try_node_toggle", {"node_id": tool_input["node_id"]})
        return {
            "nodeId": result["nodeId"],
            "allocated": result["allocated"],
            "delta": compute_delta(result["before"], result["after"]),
        }
    if name == "export_build":
        xml = bridge.call("export_xml")
        return {"code": encode_pob_code(xml)}
    raise ValueError(f"unknown tool: {name}")
