"""Shared helper for compliant homepage form searches.

Pattern (same as scraper/emt.py, generalised):
homepage -> fill origin/destination (IATA) -> pick suggestion containing the
code -> fill date -> click search -> wait -> scoped fare parse.

Never solves CAPTCHAs, never defeats bot-mitigation: block markers raise
CaptchaBlocked, missing selectors raise SelectorNotFound (honest status, the
scheduler records failed/sold_out instead of crashing or retry-storming).
"""
from __future__ import annotations

import logging
from datetime import date

from scraper.base import BlockedByStatus, CaptchaBlocked, SelectorNotFound, SoldOut
from scraper.live import MIN_FARE, REAL_CHROME_UA, new_stealth_context, parse_fares

log = logging.getLogger(__name__)

BLOCK_MARKERS = ("captcha", "are you a robot", "access denied", "request blocked",
                 "perimeterx", "akamai", "datadome", "please verify")


def _first_visible(pg, selectors: list[str]):
    for sel in selectors:
        try:
            el = pg.query_selector(sel)
            if el and el.is_visible():
                return sel, el
        except Exception:
            continue
    return None, None


def _dismiss_popups(pg) -> None:
    """Dismiss common cookie banners, login prompts, and promo modals.

    NOTE: this runs via ``document.querySelectorAll`` (raw DOM, not the
    Playwright engine), so only valid CSS selectors are allowed here —
    Playwright-only text-matcher syntax throws and would silently skip every
    rule. Button-text matching is done in JS instead.
    """
    try:
        pg.keyboard.press("Escape")
    except Exception:
        pass
    js = """() => {
      const cssHits = Array.from(document.querySelectorAll(
        '#onetrust-accept-btn-handler,' +
        '[aria-label="Close"], [class*="close" i], [class*="dismiss" i],' +
        '[class*="cookie-banner" i] button, [id*="cookie-banner" i] button,' +
        '[class*="consent-accept" i]')); // NB: never the "Manage cookies" button (it opens settings)
      const textHits = Array.from(document.querySelectorAll('button, input[type="button"]'))
        .filter(e => /^(accept all|accept|got it|allow all|allow|i agree|ok|okay|continue|close)$/i
          .test((e.innerText || e.value || '').trim()));
      for (const el of cssHits.concat(textHits)) {
        try {
          if (el.offsetParent !== null && el.offsetWidth > 0 && el.offsetHeight > 0 &&
              !el.disabled && !el.innerText.toLowerCase().includes('search')) {
            el.click();
            return true;
          }
        } catch (e) {}
      }
      return false;
    }"""
    try:
        pg.evaluate(js)
    except Exception:
        pass
    try:
        pg.wait_for_timeout(800)
    except Exception:
        pass


def _pick_suggestion(pg, code: str) -> bool:
    """Click the autocomplete suggestion for an IATA code.

    Tries ``(CODE`` first (e.g. "(DEL"), then a bare word-boundary ``CODE``
    (MUI-style options like "New Delhi DEL" carry no parens). Returns False
    when no suggestion exists — the caller falls back to Enter.
    """
    js = """(code) => {
      const els = Array.from(document.querySelectorAll(
        'ul li, [role="option"], div[role="option"], li[class*=option i], ' +
        'div[class*=airport i], div[class*=suggestion i], div[class*=autoComplete i], ' +
        'div[class*=item i], [data-testid*=airport i]'));
      const vis = els.filter(e => e.offsetParent !== null);
      let li = vis.find(e => e.innerText.toUpperCase().includes('(' + code));
      if (!li) li = vis.find(e => new RegExp('\\\\b' + code + '\\\\b').test(e.innerText.toUpperCase()));
      if (li) { li.click(); return true; } return false; }"""
    try:
        return bool(pg.evaluate(js, code))
    except Exception:
        return False


def form_search(source: str, homepage: str, origin: str, destination: str,
                flight_date: date, origin_selectors: list[str],
                dest_selectors: list[str], date_selectors: list[str],
                search_selectors: list[str], proxy: dict | None = None,
                timeout_ms: int = 60000,
                preferred_channel: str | None = None) -> dict:
    """Run one compliant homepage form search; return a raw fare payload."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        from scraper.live import goto_with_retry, launch_browser
        browser, _ = launch_browser(p, proxy, preferred_channel=preferred_channel)

        def _new_page(br):
            return new_stealth_context(br, REAL_CHROME_UA).new_page()

        try:
            browser, pg, resp = goto_with_retry(p, browser, _new_page, homepage, timeout_ms, proxy)
            if resp and 400 <= resp.status < 500:
                raise BlockedByStatus(resp.status, homepage)
            pg.wait_for_timeout(4000)
            _dismiss_popups(pg)

            o_sel, _ = _first_visible(pg, origin_selectors)
            if not o_sel:
                raise SelectorNotFound(source, origin_selectors[0] if origin_selectors else "(no origin selector)")
            pg.click(o_sel)
            pg.wait_for_timeout(800)
            # Type with real keystrokes (opens JS-framework autocomplete). Fill
            # first then type would double the text ("DELDEL") and break the IATA
            # picker, so type is primary and fill is only the fallback.
            try:
                pg.type(o_sel, origin, delay=50)
            except Exception:
                try:
                    pg.fill(o_sel, origin)
                except Exception:
                    pass
            pg.wait_for_timeout(2500)
            if not _pick_suggestion(pg, origin):
                # Some forms accept the typed code without a picker click.
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(800)

            d_sel, _ = _first_visible(pg, dest_selectors)
            if not d_sel:
                raise SelectorNotFound(source, dest_selectors[0] if dest_selectors else "(no dest selector)")
            pg.click(d_sel)
            pg.wait_for_timeout(800)
            try:
                pg.type(d_sel, destination, delay=50)
            except Exception:
                try:
                    pg.fill(d_sel, destination)
                except Exception:
                    pass
            pg.wait_for_timeout(2500)
            if not _pick_suggestion(pg, destination):
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(800)

            dt_sel, _ = _first_visible(pg, date_selectors)
            if dt_sel:
                try:
                    pg.fill(dt_sel, flight_date.strftime("%d/%m/%Y"))
                except Exception:
                    pass  # date picker widgets vary; leave default if unfillable

            s_sel, _ = _first_visible(pg, search_selectors)
            if not s_sel:
                raise SelectorNotFound(source, search_selectors[0] if search_selectors else "(no search button)")
            clicked = False
            try:
                with pg.expect_navigation(wait_until="domcontentloaded", timeout=12000):
                    pg.click(s_sel)
                    clicked = True
            except Exception:
                if not clicked:
                    try:
                        pg.click(s_sel, timeout=5000)
                    except Exception:
                        try:
                            pg.evaluate(f"() => {{ const el = document.querySelector({s_sel!r}); if (el) el.click(); }}")
                        except Exception:
                            pass
            from scraper.live import render_settle
            render_settle(pg, first_ms=10000, second_ms=6000)

            try:
                visible = pg.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")
            except Exception:
                visible = (pg.content() or "").lower()
            if any(m in visible for m in BLOCK_MARKERS):
                raise CaptchaBlocked(f"{source}: bot-mitigation on results page")
            from scraper.live import PRICE_SCOPES, extract_card_fares, parse_scoped_fares, verify_navigated
            cards = extract_card_fares(pg)
            if not verify_navigated(pg.url, homepage) and not cards:
                # Search click never left the homepage (SPA submit silently
                # failed): parsing here would report homepage marketing banners
                # ("Fares starting Rs 3,500") as fares. Honest SoldOut instead.
                raise SoldOut(f"{source}: search did not navigate to results")
            if cards:
                cheapest, n_seen = cards[0], len(cards)
            else:
                scoped = parse_scoped_fares(pg, PRICE_SCOPES)
                if not scoped:
                    raise SoldOut(f"{source}: results page but no priced fares")
                cheapest, n_seen = scoped[0], len(scoped)
            return {
                "total_fare": cheapest, "base_fare": None, "taxes": None,
                "udf": None, "convenience_fee": None, "currency": "INR",
                "decomposition_available": False, "live": True,
                "url": pg.url, "n_fares_seen": n_seen,
                "via": "homepage-form",
            }
        finally:
            browser.close()
