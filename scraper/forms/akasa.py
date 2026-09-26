"""Akasa Air homepage form flow (Next.js shell loads HTTP 200; robots allowed)."""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.akasaair.com/"
# Calibrated 2026-10-04 via live DOM dump: origin/dest inputs carry name/id
# 'From'/'To' (no placeholders); date has placeholder 'Departure date'.
ORIGIN_SELECTORS = ["input[name='From']", "#From", "input:visible >> nth=0"]
DEST_SELECTORS = ["input[name='To']", "#To", "input:visible >> nth=1"]
DATE_SELECTORS = ["input[placeholder='Departure date']", "input[name='DepartureDate']",
                  "input[placeholder*='Depart' i]"]
SEARCH_SELECTORS = ["button:has-text('Search Flights')", "button[type='submit']",
                    "button:has-text('Search')", "[class*=search i][class*=btn i]"]


def search_akasa(origin: str, destination: str, flight_date: date,
                 proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("akasa_direct", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
