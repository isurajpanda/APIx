"""Live-fetch helper: Playwright search-result scraping with honest status reporting.

Shared by all source spiders. Each spider supplies a search URL + CSS selectors;
this module navigates, detects blocks/CAPTCHAs/sold-outs, and extracts the
cheapest visible ₹ fare. Anything unexpected raises a typed exception that
``BaseScraper.run_with_retry`` converts into a proper staging-table status
(success / captcha_blocked / sold_out / failed) — never a crash.
"""
from __future__ import annotations

import logging
import re

from scraper.base import BlockedByStatus, CaptchaBlocked, SelectorNotFound, SoldOut

log = logging.getLogger(__name__)

RUPEE = re.compile(r"₹\s?([\d,]{3,})")
# Below this no genuine fare exists on our basket (cheapest sector BLR-HYD is
# ~INR 2000); lower matches are coupon/fee mentions ("flat ₹500 off").
MIN_FARE = 1500.0
# Stock Chrome UA for live fetches: declared-bot UAs are fingerprinted and
# blocked at the TLS/HTTP2 layer (ERR_HTTP2_PROTOCOL_ERROR on MMT/Goibibo).
REAL_CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BLOCK_MARKERS = ("captcha", "are you a robot", "access denied", "request blocked",
                 "perimeterx", "akamai", "datadome", "please verify")
EMPTY_MARKERS = ("no flights found", "no flights available", "sold out", "no results found")


def parse_fares(page_text: str) -> list[float]:
    """Extract all ₹ amounts from page text; cheapest first."""
    vals = []
    for m in RUPEE.finditer(page_text or ""):
        try:
            vals.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    return sorted(v for v in vals if v >= MIN_FARE)


def parse_scoped_fares(page, scopes: list[str]) -> list[float]:
    """Extract ₹ amounts only inside fare-bearing elements (fee-proof).

    Page-wide parsing picks up coupon/fee mentions ("flat ₹1500 off"); genuine
    fares live in price/listing elements. Returns sorted values, empty if none.
    """
    try:
        vals = page.evaluate(
            """(scopes) => {
              const out = [];
              for (const s of scopes) {
                document.querySelectorAll(s).forEach(e => {
                  const m = (e.innerText || '').match(/\\u20B9\\s?([\\d,]{4,})/g) || [];
                  m.forEach(x => { const v = parseFloat(x.replace(/[^\\d]/g, ''));
                                   if (v >= 1500) out.push(v); });
                });
              }
              return out;
            }""",
            scopes,
        )
    except Exception:
        return []
    return sorted(vals)


def fetch_search_result(source: str, url: str, selectors: list[str],
                        user_agent: str, proxy: dict | None = None,
                        timeout_ms: int = 45000) -> dict:
    """Navigate to a flight-search URL and return a raw fare payload.

    Raises CaptchaBlocked / SoldOut / BlockedByStatus / SelectorNotFound.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        launch_kw: dict = {"headless": True,
                           # Force HTTP/1.1: several OTAs reset HTTP/2 from headless clients.
                           "args": ["--disable-http2"]}
        if proxy:
            launch_kw["proxy"] = proxy
        browser = p.chromium.launch(**launch_kw)
        try:
            ctx = browser.new_context(user_agent=user_agent)
            page = ctx.new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if resp and resp.status in (403, 429):
                raise BlockedByStatus(resp.status, url)
            if resp and 400 <= resp.status < 500:
                raise BlockedByStatus(resp.status, url)
            # Give JS result lists a chance to render; then look for prices.
            try:
                page.wait_for_timeout(6000)
            except Exception:
                pass
            try:
                visible = page.evaluate(
                    "() => document.body ? document.body.innerText.toLowerCase() : ''"
                )
            except Exception:
                visible = (page.content() or "").lower()
            if any(m in visible for m in BLOCK_MARKERS):
                raise CaptchaBlocked(f"{source}: bot-mitigation page at {url}")
            if any(m in visible for m in EMPTY_MARKERS):
                raise SoldOut(f"{source}: no flights for query")
            found = parse_fares(page.content())
            if not found:
                # Report which selectors existed to aid field calibration.
                matched = [s for s in selectors if page.query_selector(s)]
                if not matched:
                    raise SelectorNotFound(source, selectors[0] if selectors else "(no selectors)")
                raise SoldOut(f"{source}: results page but no priced fares")
            cheapest = found[0]
            return {
                "total_fare": cheapest,
                "base_fare": None,
                "taxes": None,
                "udf": None,
                "convenience_fee": None,
                "currency": "INR",
                "decomposition_available": False,
                "live": True,
                "url": url,
                "n_fares_seen": len(found),
            }
        finally:
            browser.close()
