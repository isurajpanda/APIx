"""Air India homepage form flow (loads 200 on residential IP). Prefer the
official API in production; this form path is the compliant scraping fallback."""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.airindia.com/"
# Live DOM audit 2026-09-27: Air India booking widget is Angular Material.
# The widget uses .mat-input-element / aria-label="Origin" style attributes.
# NOTE: bundled Chromium gets TLS-hung here — preferred_channel='chrome' is set.
ORIGIN_SELECTORS = [
    "input.mat-input-element[aria-label*='Origin' i]",
    "input.mat-input-element[aria-label*='From' i]",
    "input[aria-label*='Origin' i]",
    "input[aria-label*='From' i]",
    "input[placeholder*='Origin' i]",
    "input[placeholder*='From' i]",
    "input[formcontrolname*='origin' i]",
    "input[id*='origin' i]",
    "input[id*='from' i]",
    "input[name*='origin' i]",
    # Fallback: role="combobox" (inputs carry no type attribute).
    "[role='combobox']:visible >> nth=0",
    "main [role='combobox']:visible >> nth=0",
]
DEST_SELECTORS = [
    "input.mat-input-element[aria-label*='Destination' i]",
    "input.mat-input-element[aria-label*='To' i]",
    "input[aria-label*='Destination' i]",
    "input[aria-label*='To' i]",
    "input[placeholder*='Destination' i]",
    "input[placeholder*='To' i]",
    "input[formcontrolname*='dest' i]",
    "input[id*='dest' i]",
    "input[id*='to' i]",
    "input[name*='dest' i]",
    # Live DOM 2026-10-04: BOTH inputs carry aria-label="Select origin airport"
    # pre-interaction and have NO type attribute (so input[type=text] matches
    # nothing). They do carry role="combobox" — nth=1 is the destination box.
    "[role='combobox']:visible >> nth=1",
    "main [role='combobox']:visible >> nth=1",
]
DATE_SELECTORS = [
    "input[aria-label*='Depart' i]",
    "input.mat-input-element[placeholder*='Depart' i]",
    "input[placeholder*='Depart' i]",
    "input[name*='depart' i]",
]
SEARCH_SELECTORS = [
    "button:has-text('Search Flights')",
    "button:has-text('Search flights')",
    "button:has-text('SEARCH')",
    "button:has-text('Search')",
    "button[type='submit']",
    "[class*=search-button]",
    "[class*=searchBtn]",
]


def search_airindia(origin: str, destination: str, flight_date: date,
                    proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("airindia_direct", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy, preferred_channel="chrome")
