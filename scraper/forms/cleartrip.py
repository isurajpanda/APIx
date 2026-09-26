"""Cleartrip compliant path.

Robots allows ``/flights/results`` but disallows ``/flights/search*`` — so the
sanctioned live path is the existing SEARCH_URL deep link (JS-rendered via
scraper/live.py), never /flights/search*. This module documents that decision
and exposes the allowed entry for the audit trail.
"""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.cleartrip.com/"
ALLOWED_ENTRY = "/flights/results (robots-allowed)"
DISALLOWED_ENTRY = "/flights/search* (robots-disallowed — never fetch)"

ORIGIN_SELECTORS = [
    "input[placeholder*='Where from' i]",
    "input[placeholder*='From' i]",
    "input[title*='From' i]",
    "input:visible >> nth=0",
]
DEST_SELECTORS = [
    "input[placeholder*='Where to' i]",
    "input[placeholder*='To' i]",
    "input[title*='To' i]",
    "input:visible >> nth=1",
]
DATE_SELECTORS = [
    "input[placeholder*='Depart' i]",
    "[data-testid*='depart' i]",
    "input[name*='depart' i]",
]
SEARCH_SELECTORS = [
    "button:has-text('Search flights')",
    "button:has-text('Search Flights')",
    "button:has-text('Search')",
    "button[type='submit']",
]


def search_cleartrip(origin: str, destination: str, flight_date: date,
                     proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("cleartrip", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
