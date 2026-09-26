"""Official-API stubs for providers where scraping is not viable/compliant.

* makemytrip — homepage TLS-resets automation; affiliate partnership required.
* goibibo — challenge-validation shell + timeouts; affiliate partnership required.
* airindia_express — reCAPTCHA Enterprise on homepage; never solve CAPTCHA.

Each helper reads ``<PREFIX>_API_KEY`` / ``<PREFIX>_API_URL`` env credentials.
Without credentials it returns ``(None, parked-payload)`` so the pipeline
records ``no_data`` instead of fabricating a fare or hammering a blocked site.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

REASONS = {
    "makemytrip": "MakeMyTrip TLS-resets/blocks automation; live data requires an official MMT affiliate API partnership (MMT_API_KEY).",
    "goibibo": "Goibibo serves a challenge-validation shell and times out for automation; live data requires an official Goibibo affiliate API partnership (GOIBIBO_API_KEY).",
    "airindia_express": "Air India Express homepage is reCAPTCHA Enterprise-gated; CAPTCHA solving is out of scope — official API/NDC partnership required (AIX_API_KEY).",
    "yatra": "Yatra classic form removed by the Diya-AI redesign and the XHR trigger is PerimeterX-challenged; live data requires an official Yatra affiliate API partnership (YATRA_API_KEY).",
}


def fetch_official_quote(prefix: str, origin: str, destination: str, flight_date_str: str) -> tuple[float | None, dict[str, Any]]:
    """Generic parked-unless-partnered quote fetch. Never scrapes HTML."""
    key = os.environ.get(f"{prefix}_API_KEY", "").strip()
    url = os.environ.get(f"{prefix}_API_URL", "").strip()
    source = prefix.lower()
    if not key or not url:
        return None, {"parked": True, "reason": REASONS.get(source, "official API partnership required"), "live": False}
    try:
        import json
        import urllib.request

        req = urllib.request.Request(
            url,
            data=json.dumps({"origin": origin, "destination": destination, "date": flight_date_str}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                     "User-Agent": "APIx-MoSPI-Research/1.0 (+https://mospi.gov.in)"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
        total = data.get("total_fare") or data.get("fare") or data.get("price")
        if total is None:
            return None, {"parked": True, "reason": f"{source} API schema not yet mapped", "response_keys": sorted(data.keys())[:10]}
        return float(total), {"total_fare": float(total), "live": True, "via": f"{source}_official_api"}
    except Exception as exc:  # noqa: BLE001
        log.warning("%s official API call failed: %s", source, exc)
        return None, {"parked": True, "reason": f"{source} API error: {exc}".strip()[:200]}
