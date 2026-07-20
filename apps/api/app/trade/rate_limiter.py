"""Dynamický rate limiter pro PoE trade API -- port `TradeQueryRateLimiter.lua`
z vendorovaného PoB (`vendor/PathOfBuilding/src/Classes/TradeQueryRateLimiter.lua`).

Klíčová vlastnost, kterou je nutné zachovat: limity se **nikde netvrdí natvrdo**,
čtou se z `X-Rate-Limit-*` hlaviček, které trade API vrací s každou odpovědí
(`X-Rate-Limit-Policy`, `X-Rate-Limit-Rules`, `X-Rate-Limit-<rule>`,
`X-Rate-Limit-<rule>-State` -- formát `request:window:timeout`, čárkou oddělené
"bucket" trojice). GGG tahle čísla čas od času mění; natvrdo zapsaná čísla by se
tiše rozešla s realitou. `next_request_time()` vrátí kdy je bezpečné poslat další
request; volající musí počkat, ne to ignorovat.

`limit_margin=1`: necháváme si bezpečnostní rezervu (o 1 request nižší limit,
než co server hlásí) přesně jako PoB -- řeší souběh s jinými nástroji (prohlížeč,
desktop PoB) sdílejícími stejný IP/účet rate limit.

Zjednodušeno oproti Lua originálu: timestamp historie je jediný zdroj pravdy pro
"kolik requestů jsme poslali v tomhle okně" (PoB si navíc drží ručně inkrementovaný
čítač kvůli souběžným requestům z více oken/tabů; tady je backend jednoprocesový a
requesty jdou sekvenčně, takže odvození přímo z historie je stejně korektní a bez
rizika rozjetí čítače).
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _WindowLimit:
    request: int
    timeout: int


@dataclass
class _Rule:
    limits: dict[int, _WindowLimit]


class TradeRateLimiter:
    def __init__(self, limit_margin: int = 1):
        self.limit_margin = limit_margin
        self.policies: dict[str, dict[str, _Rule]] = {}
        self.retry_after: dict[str, float] = {}
        self.last_update: dict[str, float] = {}
        self.timestamps: dict[str, list[float]] = {}

    def update_from_headers(self, headers, fallback_policy: str) -> None:
        """headers: a mapping with case-insensitive .get() (e.g. httpx.Headers)."""
        policy_name = headers.get("x-rate-limit-policy") or fallback_policy
        retry_after_header = headers.get("retry-after")

        rule_names_header = headers.get("x-rate-limit-rules") or ""
        rule_names = [r.strip().lower() for r in rule_names_header.split(",") if r.strip()]
        if not rule_names:
            return

        rules: dict[str, _Rule] = {}
        for rule_name in rule_names:
            limits_header = headers.get(f"x-rate-limit-{rule_name}") or ""
            limits = self._parse_buckets(limits_header)
            if not limits:
                continue
            if self.limit_margin > 0:
                for w in limits.values():
                    w.request = max(w.request - self.limit_margin, 1)
            rules[rule_name] = _Rule(limits=limits)

        if not rules:
            return

        self.policies[policy_name] = rules
        self.last_update[policy_name] = time.time()
        if retry_after_header:
            try:
                self.retry_after[policy_name] = time.time() + float(retry_after_header)
            except ValueError:
                pass

    @staticmethod
    def _parse_buckets(header_value: str) -> dict[int, _WindowLimit]:
        # format: "request:window:timeout,request:window:timeout,..." e.g. "8:10:60,15:60:120"
        buckets: dict[int, _WindowLimit] = {}
        for bucket in header_value.split(","):
            parts = bucket.strip().split(":")
            if len(parts) != 3:
                continue
            try:
                request, window, timeout = (int(p) for p in parts)
            except ValueError:
                continue
            buckets[window] = _WindowLimit(request=request, timeout=timeout)
        return buckets

    def next_request_time(self, policy: str) -> float:
        now = time.time()
        timestamps = self.timestamps.get(policy, [])

        if policy not in self.policies:
            # PoB's original blocks here on the theory that a request is already
            # "in flight" and its response will teach us the real limits any
            # moment -- that only matters for PoB's async multi-tab client, where
            # several requests can be outstanding at once. This client is
            # sequential: by the time next_request_time runs again, the prior
            # request has already completed and update_from_headers already ran.
            # If the policy is *still* unknown, that endpoint simply never sends
            # X-Rate-Limit-* headers (e.g. /api/trade/data/leagues) -- found live:
            # blocking for an hour here made a second, unrelated call hang.
            return now

        if policy in self.retry_after and self.retry_after[policy] >= now:
            return self.retry_after[policy]

        # Note: limit.timeout is the *penalty* length the server would apply if this
        # window's limit were exceeded (from the bucket header, e.g. "2:10:60" =
        # 2 requests per 10s, 60s penalty on violation) -- it is NOT a per-request
        # cooldown to apply proactively. The real "we got penalized" signal is a
        # 429 response / Retry-After header, already handled via self.retry_after
        # above. Using limit.timeout here unconditionally was a bug caught by
        # test_learns_limit_from_headers_and_blocks_once_exhausted: it blocked the
        # very first request after only *learning* limits, before any were used.
        next_time = now
        for rule in self.policies[policy].values():
            for window, limit in rule.limits.items():
                in_window = [t for t in timestamps if t >= now - window]
                if len(in_window) >= limit.request:
                    next_time = max(next_time, min(in_window) + window + 1)
        return next_time

    def insert_request(self, policy: str) -> None:
        self.timestamps.setdefault(policy, []).append(time.time())
        self._prune(policy)

    def wait_if_needed(self, policy: str) -> float:
        """Sleeps until next_request_time(policy), returns how long it slept (seconds)."""
        now = time.time()
        next_time = self.next_request_time(policy)
        delay = max(0.0, next_time - now)
        if delay > 0:
            time.sleep(delay)
        return delay

    def _prune(self, policy: str) -> None:
        max_window = max(
            (w for rule in self.policies.get(policy, {}).values() for w in rule.limits),
            default=3600,
        )
        now = time.time()
        self.timestamps[policy] = [t for t in self.timestamps.get(policy, []) if t >= now - max_window]


# One limiter shared by the whole process -- rate limits are per IP/account on
# GGG's side, not per-request, so state MUST persist across calls (a fresh
# limiter per call would always think it's the "first ever request").
TRADE_RATE_LIMITER = TradeRateLimiter()
