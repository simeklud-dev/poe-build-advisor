"""Klient pro veřejné (nepřihlášené) PoE trade API.

PoB (`vendor/PathOfBuilding/src/Classes/TradeQueryRequests.lua`) posílá
`Authorization: Bearer <authToken>` jen KDYŽ je uživatel přihlášený přes
oficiální PoE OAuth (`main.api.authToken`) -- bez něj hlavička chybí úplně a
request stejně projde, jen s přísnějším IP-based rate limitem (přesně to, co
běžně dělá i anonymní návštěvník pathofexile.com/trade v prohlížeči). Plán
původně počítal s `POESESSID` -- to je nesprávně, PoB ho nikde nepoužívá.
OAuth flow (registrace klienta u GGG, autorizační kód, refresh token) je
mimo rozsah tohohle MVP; když bude potřeba vyšší rate limit, přidá se později
jako vylepšení, ne jako předpoklad pro základní funkčnost.

Stat katalog (`/api/trade/data/stats`) a seznam lig (`/api/trade/data/leagues`)
jsou veřejné GET endpointy bez auth -- ID statů (`explicit.stat_...`) se
NEHARDCODUJÍ, natahují se živě a cachují v paměti procesu (mění se jen zřídka,
ale nikdy ne nikdy -- stejná filozofie jako `sanitize()` v pob-bridge.lua:
číst realitu, nehádat).
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx


def _decode_extended_text(raw: str) -> str:
    try:
        return base64.b64decode(raw).decode("utf-8")
    except Exception:
        return raw

from app.trade.rate_limiter import TRADE_RATE_LIMITER

BASE_URL = "https://www.pathofexile.com"
# Cloudflare blokuje generické User-Agenty nástrojů (httpx/curl/python-requests) --
# stejná lekce jako u poe-build-finder/apps/api/app/crawler/forum_client.py.
USER_AGENT = "poe-build-advisor/0.1 (contact: github.com/simeklud-dev; personal hobby tool)"

STATS_CACHE_TTL_SECONDS = 6 * 3600


class TradeApiError(RuntimeError):
    pass


class TradeClient:
    def __init__(self, timeout: float = 20.0):
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=timeout,
        )
        self._stats_cache: list[dict[str, Any]] | None = None
        self._stats_cache_at: float = 0.0
        self._leagues_cache: list[dict[str, Any]] | None = None
        self._leagues_cache_at: float = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TradeClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(self, method: str, url: str, policy: str, **kwargs: Any) -> httpx.Response:
        TRADE_RATE_LIMITER.wait_if_needed(policy)
        TRADE_RATE_LIMITER.insert_request(policy)
        response = self._client.request(method, url, **kwargs)
        TRADE_RATE_LIMITER.update_from_headers(response.headers, policy)
        if response.status_code == 429:
            retry_after = float(response.headers.get("retry-after", "5"))
            raise TradeApiError(f"rate limited by trade API, retry after {retry_after:.0f}s")
        if response.status_code >= 400:
            raise TradeApiError(f"trade API returned {response.status_code}: {response.text[:500]}")
        return response

    def fetch_leagues(self, realm: str = "pc") -> list[dict[str, Any]]:
        now = time.time()
        if self._leagues_cache is None or (now - self._leagues_cache_at) > STATS_CACHE_TTL_SECONDS:
            response = self._request("GET", "/api/trade/data/leagues", policy="trade-fetch-request-limit")
            self._leagues_cache = response.json().get("result", [])
            self._leagues_cache_at = now
        return [entry for entry in self._leagues_cache if entry.get("realm") == realm]

    def fetch_stats_catalog(self) -> list[dict[str, Any]]:
        """Flat list of {id, text, type} across every stat category (explicit, pseudo, ...)."""
        now = time.time()
        if self._stats_cache is None or (now - self._stats_cache_at) > STATS_CACHE_TTL_SECONDS:
            response = self._request("GET", "/api/trade/data/stats", policy="trade-fetch-request-limit")
            flat: list[dict[str, Any]] = []
            for category in response.json().get("result", []):
                for entry in category.get("entries", []):
                    flat.append(entry)
            self._stats_cache = flat
            self._stats_cache_at = now
        return self._stats_cache

    def search_stats(self, query_text: str, limit: int = 15) -> list[dict[str, Any]]:
        """Substring search over the stat catalog -- used by Claude to resolve a
        human stat description (e.g. "maximum life") to a real trade stat id
        before calling search_items."""
        needle = query_text.strip().lower()
        if not needle:
            return []
        catalog = self.fetch_stats_catalog()
        matches = [entry for entry in catalog if needle in (entry.get("text") or "").lower()]
        return matches[:limit]

    def build_query(
        self,
        stat_filters: list[dict[str, Any]],
        category: str | None = None,
        online_only: bool = True,
    ) -> dict[str, Any]:
        """stat_filters: [{"id": "explicit.stat_3299347043", "min": 80, "max": None}, ...]
        Simple "and" filter group -- NOT PoB's DPS/Life-weighted search (that's a
        1300+ line PoE-specific algorithm, out of scope for this MVP; a future
        iteration could port WeightedRatioOutputs if the plain filter isn't enough)."""
        filters = []
        for f in stat_filters:
            value: dict[str, Any] = {}
            if f.get("min") is not None:
                value["min"] = f["min"]
            if f.get("max") is not None:
                value["max"] = f["max"]
            filters.append({"id": f["id"], "value": value, "disabled": False})

        query: dict[str, Any] = {
            "query": {
                "stats": [{"type": "and", "filters": filters}],
            },
            "sort": {"price": "asc"},
        }
        if online_only:
            query["query"]["status"] = {"option": "online"}
        if category:
            query["query"]["filters"] = {"type_filters": {"filters": {"category": {"option": category}}}}
        return query

    def search(self, league: str, query: dict[str, Any], realm: str = "pc") -> dict[str, Any]:
        url = f"/api/trade/search/{league}" if realm == "pc" else f"/api/trade/search/{realm}/{league}"
        response = self._request("POST", url, policy="trade-search-request-limit", json=query)
        data = response.json()
        if data.get("error"):
            raise TradeApiError(f"{data['error'].get('code')}: {data['error'].get('message')}")
        return data

    def fetch_items(self, item_ids: list[str], query_id: str, max_items: int = 10) -> list[dict[str, Any]]:
        ids = item_ids[:max_items]
        if not ids:
            return []
        items: list[dict[str, Any]] = []
        for start in range(0, len(ids), 10):
            block = ids[start : start + 10]
            url = f"/api/trade/fetch/{','.join(block)}?query={query_id}"
            response = self._request("GET", url, policy="trade-fetch-request-limit")
            data = response.json()
            for entry in data.get("result", []) or []:
                listing = entry.get("listing", {})
                price = listing.get("price") or {}
                # extended.text is base64 (matches PoB's
                # common.base64.decode(trade_entry.item.extended.text)) -- found
                # live, without this item_text is unreadable base64 gibberish.
                raw_text = entry.get("item", {}).get("extended", {}).get("text")
                item_text = _decode_extended_text(raw_text) if raw_text else entry.get("item", {}).get("name")
                items.append(
                    {
                        "id": entry.get("id"),
                        "item_text": item_text,
                        "price_amount": price.get("amount"),
                        "price_currency": price.get("currency"),
                        "whisper": listing.get("whisper"),
                        "seller_account": (listing.get("account") or {}).get("name"),
                        "item_level": entry.get("item", {}).get("ilvl"),
                    }
                )
        return items

    def search_stat_by_id(self, stat_id: str) -> dict[str, Any] | None:
        """Exact-id lookup, used to validate a stat id Claude picked from a
        prior search_stats call before spending a real search request on it."""
        for entry in self.fetch_stats_catalog():
            if entry.get("id") == stat_id:
                return entry
        return None

    def search_items(
        self,
        league: str,
        stat_filters: list[dict[str, Any]],
        category: str | None = None,
        max_results: int = 10,
        realm: str = "pc",
    ) -> dict[str, Any]:
        query = self.build_query(stat_filters, category=category)
        result = self.search(league, query, realm=realm)
        total = result.get("total", 0)
        if not result.get("result"):
            return {"total": total, "items": []}
        items = self.fetch_items(result["result"], result["id"], max_items=max_results)
        return {"total": total, "items": items, "query_id": result["id"]}


# Shared across the whole process, same reasoning as TRADE_RATE_LIMITER: reuses
# the httpx connection pool and the stats/leagues cache instead of re-fetching
# the ~thousands-of-entries stat catalog on every single tool call.
TRADE_CLIENT = TradeClient()
