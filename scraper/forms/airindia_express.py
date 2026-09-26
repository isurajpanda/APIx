"""Air India Express homepage form flow."""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.airindiaexpress.com/"
# Live DOM 2026-09-27: The homepage has a sticky header (#new-header-with-stepper)
# that intercepts clicks. input:visible >> nth=0 resolves to a search-bar popup
# inside that header. We scope to the booking widget outside the header.
ORIGIN_SELECTORS = [
    "main input[placeholder*='Origin' i]",
    "main input[placeholder*='From' i]",
    "main input[aria-label*='Origin' i]",
    "main input[aria-label*='From' i]",
    "main input[name*='origin' i]",
    "div[class*='booking' i] input:visible >> nth=0",
    "section[class*='search' i] input:visible >> nth=0",
    "form input:visible >> nth=0",
]
DEST_SELECTORS = [
    "main input[placeholder*='Destination' i]",
    "main input[placeholder*='To' i]",
    "main input[aria-label*='Destination' i]",
    "main input[aria-label*='To' i]",
    "main input[name*='dest' i]",
    "div[class*='booking' i] input:visible >> nth=1",
    "section[class*='search' i] input:visible >> nth=1",
    "form input:visible >> nth=1",
]
DATE_SELECTORS = [
    "main input[placeholder*='Depart' i]",
    "main input[name*='depart' i]",
    "main input[aria-label*='Depart' i]",
]
SEARCH_SELECTORS = [
    "main button:has-text('Search Flights')",
    "main button:has-text('Search')",
    "main button[type='submit']",
    "form button[type='submit']",
    "button:has-text('Search Flights')",
    "button:has-text('Search')",
]


def search_airindia_express(origin: str, destination: str, flight_date: date,
                            proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("airindia_express", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
