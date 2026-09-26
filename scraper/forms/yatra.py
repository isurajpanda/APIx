"""Yatra homepage form flow — ARCHIVED attempt (2026-10-04).

The classic origin/dest form (BE_flight_origin_city et al.) is gone after the
Diya-AI redesign (MUI combos + NL query box), so these selectors no longer
match and the spider is parked on the affiliate-API path instead.
Kept for reference in case the classic form returns. IMPORTANT: never hit the
PerimeterX-challenged ``flight.yatra.com/air-search-ui/dom2/trigger`` XHR
directly.
"""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.yatra.com/"
ORIGIN_SELECTORS = ["input[id*='origin' i]", "input[placeholder*='From' i]", "#BE_flight_origin_city"]
DEST_SELECTORS = ["input[id*='dest' i]", "input[placeholder*='To' i]", "#BE_flight_arrival_city"]
DATE_SELECTORS = ["input[id*='depart' i]", "input[placeholder*='Depart' i]", "#BE_flight_depart_date"]
SEARCH_SELECTORS = ["input[value*='Search' i][type='button']", "button:has-text('Search')", "#BE_flight_flsearch_btn"]


def search_yatra(origin: str, destination: str, flight_date: date,
                 proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("yatra", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
