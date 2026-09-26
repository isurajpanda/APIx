"""Ixigo homepage form flow — ARCHIVED, NEVER WIRED (2026-10-04).

robots.txt disallows /search/result/ and the flow is reCAPTCHA-gated, so this
module is intentionally NOT referenced by IxigoScraper (no APIX_SCRAPE_PARKED
backdoor — that hole was closed). Kept for reference only; live Ixigo data
comes exclusively from scraper/ixigo_api.py partnership credentials."""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.ixigo.com/flights"
ORIGIN_SELECTORS = [
    "input[placeholder*='From' i]",
    "div:has-text('From') >> input",
    "input:visible >> nth=0",
]
DEST_SELECTORS = [
    "input[placeholder*='To' i]",
    "div:has-text('To') >> input",
    "input:visible >> nth=1",
]
DATE_SELECTORS = [
    "input[placeholder*='Depart' i]",
    "div:has-text('Departure') >> input",
]
SEARCH_SELECTORS = [
    "button:has-text('Search Flights')",
    "button:has-text('Search')",
    "button[type='submit']",
]


def search_ixigo(origin: str, destination: str, flight_date: date,
                 proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("ixigo", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
