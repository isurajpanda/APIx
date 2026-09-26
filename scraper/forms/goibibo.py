"""Goibibo homepage form flow."""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.goibibo.com/flights/"
ORIGIN_SELECTORS = [
    "input[id*='autoSuggest-open' i]",
    "p:has-text('Enter city or airport') >> nth=0",
    "input[placeholder*='From' i]",
    "input:visible >> nth=0",
]
DEST_SELECTORS = [
    "input[id*='autoSuggest-open' i] >> nth=1",
    "p:has-text('Enter city or airport') >> nth=1",
    "input[placeholder*='To' i]",
    "input:visible >> nth=1",
]
DATE_SELECTORS = [
    "div[class*='dcalendar' i]",
    "div[class*='DayPicker' i]",
    "input[placeholder*='Depart' i]",
]
SEARCH_SELECTORS = [
    "span:has-text('SEARCH FLIGHTS')",
    "span:has-text('Search Flights')",
    "button:has-text('Search')",
    "[class*=searchBtn i]",
]


def search_goibibo(origin: str, destination: str, flight_date: date,
                   proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("goibibo", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
