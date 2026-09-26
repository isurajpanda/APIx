"""Form-driven live search for EaseMyTrip (proven path — see probe_emt.py).

EMT serves results only after its homepage search form is submitted
(DEL -> hidden code, BOM -> hidden code, DD/MM/YYYY date). Direct deep links
with guessed `srch` formats land on an idle shell, so this module drives the
real form: airport autocomplete pickers + date fill + search click.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from scraper.base import BlockedByStatus, CaptchaBlocked, SelectorNotFound, SoldOut
from scraper.live import MIN_FARE, REAL_CHROME_UA, parse_fares

log = logging.getLogger(__name__)

BLOCK_MARKERS = ("captcha", "are you a robot", "access denied", "request blocked",
                 "perimeterx", "akamai", "datadome", "please verify")


def _pick_airport(pg, box_sel: str, field_sel: str, code: str, city: str) -> None:
    """Open an airport picker, type the IATA code, click the code suggestion.

    Matches on "(DEL" style IATA fragment — robust to city-name spelling
    (Delhi/Bengaluru-vs-Bangalore).
    """
    pg.evaluate(f"() => document.querySelector('{box_sel}').click()")
    pg.wait_for_timeout(1200)
    pg.fill(field_sel, code)
    pg.wait_for_timeout(2500)
    clicked = pg.evaluate(
        f"() => {{ const li = Array.from(document.querySelectorAll('ul li'))"
        f".find(e => e.offsetParent !== null && e.innerText.toUpperCase().includes('({code}'));"
        f" if (li) {{ li.click(); return true; }} return false; }}"
    )
    if not clicked:
        raise SelectorNotFound("easemytrip", f"suggestion for {code}")
    pg.wait_for_timeout(800)


def search_easymytrip(origin: str, destination: str, flight_date: date,
                      proxy: dict | None = None, timeout_ms: int = 60000) -> dict:
    """Run a live DEL->BOM-style search; return a raw fare payload."""
    from playwright.sync_api import sync_playwright

    city = {"DEL": "DELHI", "BOM": "MUMBAI", "BLR": "BENGALURU", "CCU": "KOLKATA",
            "HYD": "HYDERABAD", "MAA": "CHENNAI"}
    with sync_playwright() as p:
        kw: dict = {"headless": True, "args": ["--disable-http2"]}
        if proxy:
            kw["proxy"] = proxy
        browser = p.chromium.launch(**kw)
        try:
            from scraper.live import new_stealth_context
            pg = new_stealth_context(browser, REAL_CHROME_UA).new_page()
            resp = pg.goto("https://www.easemytrip.com/", wait_until="domcontentloaded",
                           timeout=timeout_ms)
            if resp and 400 <= resp.status < 500:
                raise BlockedByStatus(resp.status, "easemytrip.com")
            pg.wait_for_timeout(4000)
            _pick_airport(pg, "#FromSector_show", "#a_FromSector_show", origin, city[origin])
            _pick_airport(pg, "#Editbox13_show", "#a_Editbox13_show", destination,
                          city[destination])
            pg.fill("#ddate", flight_date.strftime("%d/%m/%Y"))
            with pg.expect_navigation(wait_until="domcontentloaded", timeout=30000):
                pg.evaluate(
                    "() => { const c = ['input.srchBtnSe', 'input.srchBtnmultcty']"
                    ".flatMap(s => Array.from(document.querySelectorAll(s)))"
                    ".find(e => e.offsetParent !== null);"
                    " if (!c) throw new Error('no visible search button'); c.click(); }"
                )
            pg.wait_for_timeout(12000)
            try:
                visible = pg.evaluate(
                    "() => document.body ? document.body.innerText.toLowerCase() : ''"
                )
            except Exception:
                visible = (pg.content() or "").lower()
            if any(m in visible for m in BLOCK_MARKERS):
                raise CaptchaBlocked("easemytrip: bot-mitigation on results page")
            fares = parse_fares(pg.content())
            try:
                from scraper.live import parse_scoped_fares
                scoped = parse_scoped_fares(pg, ["[class*=price i]", "[class*=listing i]"])
                if scoped:
                    fares = scoped
            except Exception:
                pass
            if not fares:
                raise SoldOut("easemytrip: results page but no priced fares")
            return {
                "total_fare": fares[0], "base_fare": None, "taxes": None,
                "udf": None, "convenience_fee": None, "currency": "INR",
                "decomposition_available": False, "live": True,
                "url": pg.url, "n_fares_seen": len(fares),
            }
        finally:
            browser.close()
