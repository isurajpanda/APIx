"""IndiGo homepage form flow (Angular shell loads 200 on residential IP;
content APIs stalled for automation on datacenter IP). Best-effort selectors —
missing DOM raises SelectorNotFound (honest failed status, no bypass)."""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.goindigo.in/"
ORIGIN_SELECTORS = [
    "input[placeholder*='From' i]",
    "input[aria-label*='From' i]",
    "input[name*='origin' i]",
    "[formcontrolname*='origin' i]",
    ".hp-src-ipt",
    "input:visible >> nth=0",
]
DEST_SELECTORS = [
    "input[placeholder*='To' i]",
    "input[aria-label*='To' i]",
    "input[name*='dest' i]",
    "[formcontrolname*='dest' i]",
    ".hp-dest-ipt",
    "input:visible >> nth=1",
]
DATE_SELECTORS = [
    "input[placeholder*='Depart' i]",
    "[aria-label*='Depart' i]",
    "input[formcontrolname*='date' i]",
    ".hp-date-ipt",
]
SEARCH_SELECTORS = [
    "button:has-text('Search Flight')",
    "button:has-text('Search Flights')",
    "button[type='submit']",
    "button:has-text('Search')",
    "[class*=search i][class*=btn i]",
]


def search_indigo(origin: str, destination: str, flight_date: date,
                  proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("indigo_direct", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
