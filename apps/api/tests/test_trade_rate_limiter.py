import time

from app.trade.rate_limiter import TradeRateLimiter


def _headers(limits: str, rules: str = "ip", policy: str = "trade-search-request-limit", retry_after: str | None = None):
    d = {
        "x-rate-limit-policy": policy,
        "x-rate-limit-rules": rules,
        f"x-rate-limit-{rules}": limits,
    }
    if retry_after:
        d["retry-after"] = retry_after
    return d


def test_first_request_is_never_blocked():
    limiter = TradeRateLimiter()
    assert limiter.next_request_time("trade-search-request-limit") <= time.time() + 0.01


def test_unknown_policy_never_blocks_in_this_sequential_client():
    # Some real endpoints (e.g. /api/trade/data/leagues) never send X-Rate-Limit-*
    # headers at all -- found live. A prior request having been made without
    # learning a policy must not stall a later, unrelated call under the same
    # policy name (client is sequential: no request is ever "still in flight"
    # by the time this is checked again).
    limiter = TradeRateLimiter()
    limiter.insert_request("trade-search-request-limit")
    assert limiter.next_request_time("trade-search-request-limit") <= time.time() + 0.01


def test_learns_limit_from_headers_and_blocks_once_exhausted():
    limiter = TradeRateLimiter(limit_margin=0)
    # server says: 2 requests per 10 second window
    limiter.update_from_headers(_headers("2:10:60"), "trade-search-request-limit")
    assert limiter.next_request_time("trade-search-request-limit") <= time.time() + 0.01

    limiter.insert_request("trade-search-request-limit")
    limiter.insert_request("trade-search-request-limit")
    # limit (2) reached within the 10s window -- must now wait
    next_time = limiter.next_request_time("trade-search-request-limit")
    assert next_time > time.time()
    assert next_time <= time.time() + 11  # window(10) + 1s slack, not longer


def test_limit_margin_reserves_safety_headroom():
    limiter = TradeRateLimiter(limit_margin=1)
    # server allows 5, we should only ever use 4
    limiter.update_from_headers(_headers("5:60:120"), "trade-search-request-limit")
    for _ in range(4):
        limiter.insert_request("trade-search-request-limit")
    assert limiter.next_request_time("trade-search-request-limit") > time.time()


def test_retry_after_takes_priority():
    limiter = TradeRateLimiter()
    limiter.update_from_headers(_headers("100:60:120", retry_after="30"), "trade-search-request-limit")
    next_time = limiter.next_request_time("trade-search-request-limit")
    assert next_time >= time.time() + 29


def test_old_requests_age_out_of_the_window():
    limiter = TradeRateLimiter(limit_margin=0)
    limiter.update_from_headers(_headers("1:1:5"), "trade-search-request-limit")  # 1 req per 1s window
    limiter.insert_request("trade-search-request-limit")
    time.sleep(1.1)
    # the 1s window has elapsed -- should be allowed again
    assert limiter.next_request_time("trade-search-request-limit") <= time.time() + 0.1


def test_independent_policies_do_not_interfere():
    limiter = TradeRateLimiter(limit_margin=0)
    limiter.update_from_headers(_headers("1:60:120"), "trade-search-request-limit")
    limiter.insert_request("trade-search-request-limit")
    # fetch policy untouched -- first request there should still be immediate
    assert limiter.next_request_time("trade-fetch-request-limit") <= time.time() + 0.01
