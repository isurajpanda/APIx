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

RUPEE = re.compile(r"(?:₹|Rs\.?|INR)\s?([\d,]{3,})", re.IGNORECASE)
# Below this no genuine fare exists on our basket (cheapest sector BLR-HYD is
# ~INR 2000); lower matches are coupon/fee mentions ("flat ₹500 off").
MIN_FARE = 1500.0
# Offer-context words: an amount whose ±40-char window contains one of these
# (whole-word) is coupon/fee/marketing text, NOT a fare ("flat ₹3,000 off",
# "₹1,500 cancellation fee", "Fares starting ₹3,500"). Deliberately excludes
# 'fee'/'taxes' — genuine totals often read "₹5,200 incl. taxes".
# NOTE: this literal is interpolated into the JS below (new RegExp) so the
# browser-side filter is byte-identical to the Python one. Keep both in sync.
OFFER_WORDS = r"\b(off|coupon|cashback|discount|promo|starting|save|emi|cancellation)\b"
OFFER_RE = re.compile(OFFER_WORDS, re.IGNORECASE)
OFFER_WINDOW = 40

# Result-card containers (one price per card = one flight option). Broad on
# purpose — extract_card_fares() only trusts them when >=2 are visible.
CARD_SCOPES = [
    "[class*=result-card i]", "[class*=flight-card i]", "[class*=farecard i]",
    "[class*=fare-card i]", "[class*=itinerar i]", "[class*=journey-card i]",
    "[class*=listing-card i]", "[class*=flight-result i]", "[class*=result-row i]",
    "[class*=search-result i]", "[data-testid*=flight-result i]",
    "[data-testid*=result-card i]",
]
PRICE_SCOPES = ["[class*=price i]", "[class*=fare i]", "[class*=amount i]"]


def _offer_ok(window_text: str) -> bool:
    """True when the text around an amount looks like a genuine fare context."""
    return not OFFER_RE.search(window_text or "")
# Stock Chrome UA for live fetches: declared-bot UAs are fingerprinted and
# blocked at the TLS/HTTP2 layer (ERR_HTTP2_PROTOCOL_ERROR on MMT/Goibibo).
REAL_CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BLOCK_MARKERS = ("captcha", "are you a robot", "access denied", "request blocked",
                 "perimeterx", "akamai", "datadome", "please verify")
EMPTY_MARKERS = ("no flights found", "no flights available", "sold out", "no results found")

# Applied to every live browser context: strips the most common headless tells.
# Won't beat Akamai/PerimeterX alone, but lifts success on mid-tier defenses.
STEALTH_JS = """() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
  window.chrome = window.chrome || { runtime: {} };
  const origQuery = window.navigator.permissions.query;
  window.navigator.permissions.query = (p) => (
    p.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : origQuery(p)
  );
}"""


def new_stealth_context(browser, user_agent: str):
    """Create a browser context with stealth patches + realistic viewport/locale."""
    ctx = browser.new_context(
        user_agent=user_agent, locale="en-IN", timezone_id="Asia/Kolkata",
        viewport={"width": 1366, "height": 768},
    )
    ctx.add_init_script(STEALTH_JS)
    return ctx


def launch_browser(p, proxy: dict | None = None, preferred_channel: str | None = None):
    """Launch Chromium; fall back to installed real Chrome if stock launch fails.

    Some airline sites TLS-fingerprint the bundled Chromium build
    (ERR_CONNECTION_RESET on goto) while accepting real Chrome. The fallback
    costs no extra site hit (it happens before any navigation).
    Returns ``(browser, via_channel)``. ``APIX_PLAYWRIGHT_CHANNEL`` forces a
    channel (e.g. ``chrome``) when set.
    """
    import os

    kw: dict = {"headless": True,
                # Force HTTP/1.1: several OTAs reset HTTP/2 from headless clients.
                "args": ["--disable-http2"]}
    if proxy:
        kw["proxy"] = proxy
    forced = preferred_channel or os.environ.get("APIX_PLAYWRIGHT_CHANNEL", "").strip()
    if forced:
        try:
            return p.chromium.launch(channel=forced, **kw), True
        except Exception:
            pass
    try:
        return p.chromium.launch(**kw), False
    except Exception as first_exc:
        try:
            return p.chromium.launch(channel="chrome", **kw), True
        except Exception:
            raise first_exc


def _is_client_reject(exc: Exception) -> bool:
    """True for TLS-fingerprint rejections where a real-Chrome retry is worth one shot."""
    msg = str(exc)
    return any(m in msg for m in ("ERR_CONNECTION_RESET", "ERR_EMPTY_RESPONSE",
                                  "ERR_CONNECTION_CLOSED", "ERR_SSL"))


def goto_with_retry(p, browser, new_page, url: str, timeout_ms: int,
                      proxy: dict | None = None):
    """Goto with one real-Chrome retry on TLS-fingerprint rejections.

    ``new_page(browser)`` builds the stealth page. Returns
    ``(browser, page, response)``. The retry fires only when the first hit
    never got a response (reset/closed), so a search stays ≤2 polite hits.
    Raises the original error if real Chrome is unavailable.
    """
    page = new_page(browser)
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return browser, page, resp
    except Exception as exc:
        if not _is_client_reject(exc):
            raise
        for closer in (getattr(page, "close", None), getattr(browser, "close", None)):
            try:
                if closer:
                    closer()
            except Exception:
                pass
        kw: dict = {"headless": True, "args": ["--disable-http2"]}
        if proxy:
            kw["proxy"] = proxy
        browser2 = p.chromium.launch(channel="chrome", **kw)  # raises if no real Chrome
        page2 = new_page(browser2)
        resp2 = page2.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return browser2, page2, resp2


def resolve_fares(page, source: str, selectors: list[str],
                    card_scopes: list[str] | None = None) -> tuple[float, int]:
    """Pick (cheapest, count) with the card-first rule.

    1. Result cards (>=1): one offer-filtered price per card → cheapest card.
    2. Spiders with fare-specific selectors (no ``body`` catch-all): scoped
       offer-filtered min — page-wide parsing picks up fee/coupon mentions
       (e.g. Cleartrip "₹1,500 cancellation fee") and would fake a SUCCESS.
    3. Otherwise: offer-filtered page-wide min with scoped refinement.
    Raises SoldOut / SelectorNotFound when no genuine fare exists.
    """
    if card_scopes is not None:
        cards = extract_card_fares(page, card_scopes)
        if cards:
            return cards[0], len(cards)
    specific = [s for s in (selectors or []) if s.strip().lower() != "body"]
    if specific and len(specific) == len(selectors or []):
        scoped = parse_scoped_fares(page, specific)
        if scoped:
            return scoped[0], len(scoped)
        matched = [s for s in specific if page.query_selector(s)]
        if not matched:
            raise SelectorNotFound(source, specific[0] if specific else "(no selectors)")
        raise SoldOut(f"{source}: results page but no priced fares in fare elements")
    found = parse_fares(page.content())
    if not found:
        matched = [s for s in (selectors or []) if page.query_selector(s)]
        if not matched:
            raise SelectorNotFound(source, selectors[0] if selectors else "(no selectors)")
        raise SoldOut(f"{source}: results page but no priced fares")
    try:
        scoped = parse_scoped_fares(page, ["[class*=price i]", "[class*=fare i]", "[class*=listing i]"])
        if scoped:
            return scoped[0], len(scoped)
    except Exception:
        pass
    return found[0], len(found)


def render_settle(page, first_ms: int = 6000, second_ms: int = 8000) -> None:
    """Let JS result lists render; scroll + second chance before giving up."""
    try:
        page.wait_for_timeout(first_ms)
    except Exception:
        pass
    try:
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(second_ms)
    except Exception:
        pass


def parse_fares(page_text: str) -> list[float]:
    """Extract all ₹ amounts from page text, offer-context filtered, cheapest first."""
    text = page_text or ""
    vals = []
    for m in RUPEE.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if v < MIN_FARE:
            continue
        window = text[max(0, m.start() - OFFER_WINDOW): m.end() + OFFER_WINDOW]
        if not _offer_ok(window):
            continue
        vals.append(v)
    return sorted(vals)


def parse_scoped_fares(page, scopes: list[str]) -> list[float]:
    """Extract ₹ amounts only inside fare-bearing elements (fee-proof).

    Page-wide parsing picks up coupon/fee mentions ("flat ₹1500 off"); genuine
    fares live in price/listing elements. Each amount is offer-context filtered
    (±40 chars, same OFFER_WORDS rule as Python). The old plain-number fallback
    is GONE: it caught flight numbers ("6E 2034") and times as fake fares.
    Returns sorted values, empty if none.
    """
    js = """(args) => {
              const scopes = args.scopes, offRe = new RegExp(args.offerWords, 'i');
              const out = [];
              for (const s of scopes) {
                document.querySelectorAll(s).forEach(e => {
                  const txt = (e.innerText || '');
                  const re = /(?:\\u20B9|Rs\\.?|INR)\\s?([\\d,]{3,})/gi;
                  let m;
                  while ((m = re.exec(txt)) !== null) {
                    const v = parseFloat(m[1].replace(/[^\\d]/g, ''));
                    if (v < 1500) continue;
                    const win = txt.slice(Math.max(0, m.index - 40), m.index + m[0].length + 40);
                    if (offRe.test(win)) continue;
                    out.push(v);
                  }
                });
              }
              return out;
            }"""
    try:
        vals = page.evaluate(js, {"scopes": scopes, "offerWords": OFFER_WORDS})
    except Exception:
        return []
    return sorted(vals)


def extract_card_fares(page, card_scopes: list[str] | None = None,
                       price_scopes: list[str] | None = None) -> list[float]:
    """One price per result card (one flight option), offer-filtered.

    Returns sorted per-card fares, empty when no cards resolve. Card containers
    that only hold coupon/marketing amounts contribute nothing, and a page with
    no cards at all (homepage shells, promo pages) yields [] — never homepage
    banner prices misreported as search results.
    """
    js = """(args) => {
              const offRe = new RegExp(args.offerWords, 'i');
              const priceSel = args.priceScopes.join(',');
              const cards = [];
              for (const s of args.cardScopes) {
                document.querySelectorAll(s).forEach(e => {
                  if (e.offsetParent !== null) cards.push(e);
                });
              }
              const out = [];
              for (const card of cards) {
                let el = null;
                try {
                  if (card.matches(priceSel)) el = card;
                  else el = card.querySelector(priceSel);
                } catch (e) { el = card; }
                if (!el) continue;
                const txt = (el.innerText || '');
                const re = /(?:\\u20B9|Rs\\.?|INR)\\s?([\\d,]{3,})/gi;
                let m;
                while ((m = re.exec(txt)) !== null) {
                  const v = parseFloat(m[1].replace(/[^\\d]/g, ''));
                  if (v < 1500) continue;
                  const win = txt.slice(Math.max(0, m.index - 40), m.index + m[0].length + 40);
                  if (offRe.test(win)) continue;
                  out.push(v);
                  break; // one price per card
                }
              }
              return out;
            }"""
    try:
        vals = page.evaluate(js, {
            "cardScopes": card_scopes or CARD_SCOPES,
            "priceScopes": price_scopes or PRICE_SCOPES,
            "offerWords": OFFER_WORDS,
        })
    except Exception:
        return []
    return sorted(vals)


def verify_navigated(page_url: str, homepage: str) -> bool:
    """True when the browser left the homepage (trailing-slash/query-insensitive)."""
    norm = lambda u: (u or "").split("?")[0].rstrip("/")
    return norm(page_url) != norm(homepage)


def fetch_search_result(source: str, url: str, selectors: list[str],
                        user_agent: str, proxy: dict | None = None,
                        timeout_ms: int = 45000) -> dict:
    """Navigate to a flight-search URL and return a raw fare payload.

    Raises CaptchaBlocked / SoldOut / BlockedByStatus / SelectorNotFound.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, _ = launch_browser(p, proxy)
        try:
            def _new_page(br):
                return new_stealth_context(br, user_agent).new_page()

            browser, page, resp = goto_with_retry(p, browser, _new_page, url, timeout_ms, proxy)
            if resp and resp.status in (403, 429):
                raise BlockedByStatus(resp.status, url)
            if resp and 400 <= resp.status < 500:
                raise BlockedByStatus(resp.status, url)
            # Give JS result lists a chance to render; then look for prices.
            render_settle(page)
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
            no_body = bool(selectors) and all(s.strip().lower() != "body" for s in selectors)
            cheapest, n_seen = resolve_fares(
                page, source, selectors, CARD_SCOPES if no_body else None)
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
                "n_fares_seen": n_seen,
            }
        finally:
            browser.close()
