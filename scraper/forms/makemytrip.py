"""MakeMyTrip homepage form flow."""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.makemytrip.com/flights/"
ORIGIN_SELECTORS = [
    "input[id='fromCity']",
    "label[for='fromCity']",
    "input[placeholder*='From' i]",
    "input:visible >> nth=0",
]
DEST_SELECTORS = [
    "input[id='toCity']",
    "label[for='toCity']",
    "input[placeholder*='To' i]",
    "input:visible >> nth=1",
]
DATE_SELECTORS = [
    "input[id='departure']",
    "label[for='departure']",
    "[data-cy='departureDate']",
]
SEARCH_SELECTORS = [
    "a:has-text('Search')",
    "button:has-text('Search')",
    "[data-cy='submit']",
    ".widgetSearchBtn",
]


def search_makemytrip(origin: str, destination: str, flight_date: date,
                      proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("makemytrip", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
