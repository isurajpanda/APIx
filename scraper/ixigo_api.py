"""Ixigo compliant data path: official API / affiliate partnership only.

Why this module exists
----------------------
Ixigo's ``robots.txt`` explicitly disallows the flight-search path used by the
generic scraper::

    Disallow: /search/result/

and the search experience is gated by reCAPTCHA. Per ``SCRAPING_ETHICS.md``
(no CAPTCHA solving, robots.txt honoured, ToS-compliant) APIx must NOT scrape
Ixigo search-result pages, solve its CAPTCHA, or route around its
bot-mitigation. This module is the ONLY sanctioned Ixigo path: an official
Ixigo affiliate / API integration supplied via environment credentials.

Configure (all optional; absent credentials => parked ``no_data`` quote)::

    IXIGO_API_KEY=...
    IXIGO_API_URL=https://api.ixigo.com/...   # provided by Ixigo partnership
    IXIGO_AFFILIATE_ID=...

Behaviour
---------
* No credentials -> returns ``(None, {"parked": ..., "reason": ...})`` so the
  pipeline records ``no_data`` instead of fabricating a fare.
* With credentials -> placeholder POSTs origin/destination/date to the
  partnership endpoint. Wire the exact schema Ixigo supplies; the stub raises
  ``NotImplementedError``-as-payload until the partnership schema is filled in,
  rather than silently falling back to scraping.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

PARKED_REASON = (
    "ixigo search path is robots-disallowed (/search/result/) and CAPTCHA-gated; "
    "scraping is disabled by policy. Supply IXIGO_API_KEY via an official "
    "Ixigo affiliate/API partnership to enable compliant data."
)


def fetch_official_quote(origin: str, destination: str, flight_date_str: str) -> tuple[float | None, dict[str, Any]]:
    """Fetch one Ixigo quote via the official partnership API.

    Returns ``(total_fare_or_None, payload_dict)``. Never scrapes HTML.
    """
    api_key = os.environ.get("IXIGO_API_KEY", "").strip()
    api_url = os.environ.get("IXIGO_API_URL", "").strip()
    if not api_key or not api_url:
        return None, {"parked": True, "reason": PARKED_REASON, "live": False}
    # Partnership schema goes here — fail loudly until wired, never scrape.
    try:
        import urllib.request
        import json

        req = urllib.request.Request(
            api_url,
            data=json.dumps(
                {"origin": origin, "destination": destination, "date": flight_date_str}
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "APIx-MoSPI-Research/1.0 (+https://mospi.gov.in)",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
        total = data.get("total_fare") or data.get("fare") or data.get("price")
        if total is None:
            return None, {"parked": True, "reason": "ixigo API schema not yet mapped", "response_keys": sorted(data.keys())[:10]}
        return float(total), {"total_fare": float(total), "live": True, "via": "ixigo_official_api"}
    except Exception as exc:  # noqa: BLE001 — report as payload, never crash
        log.warning("ixigo official API call failed: %s", exc)
        return None, {"parked": True, "reason": f"ixigo API error: {exc}".strip()[:200]}
