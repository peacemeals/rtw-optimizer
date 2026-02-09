"""Google Flights search via SerpAPI (structured JSON API).

Provides reliable flight pricing without browser automation or scraping risk.
Requires SERPAPI_API_KEY environment variable. Degrades gracefully to None when
the key is not set or the API is unavailable.
"""

from __future__ import annotations

import logging
import os
from datetime import date as Date
from typing import Optional

import requests

from rtw.scraper.google_flights import FlightPrice, _CARRIER_IATA, _rate_limit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERPAPI_BASE_URL = "https://serpapi.com/search"
_SERPAPI_ENGINE = "google_flights"
_SERPAPI_TIMEOUT_S = 15

_CABIN_MAP = {
    "economy": 1,
    "premium_economy": 2,
    "business": 3,
    "first": 4,
}

# SerpAPI stops param: 0=any, 1=nonstop, 2=1-stop-or-fewer, 3=2-stops-or-fewer
_STOPS_MAP = {
    0: 1,   # nonstop only
    1: 2,   # 1 stop or fewer
    2: 3,   # 2 stops or fewer
}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SerpAPIError(Exception):
    """Base exception for SerpAPI errors."""


class SerpAPIAuthError(SerpAPIError):
    """HTTP 401 — invalid or missing API key."""


class SerpAPIQuotaError(SerpAPIError):
    """HTTP 429 — monthly search quota exceeded."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def serpapi_available() -> bool:
    """Check if SERPAPI_API_KEY is set and non-empty."""
    return bool(os.environ.get("SERPAPI_API_KEY", "").strip())


def search_serpapi(
    origin: str,
    dest: str,
    date: Date,
    cabin: str = "business",
    max_stops: Optional[int] = None,
    oneworld_only: bool = True,
) -> Optional[FlightPrice]:
    """Search Google Flights via SerpAPI.

    Returns the cheapest flight found, or None if unavailable.
    Raises SerpAPIAuthError on 401, SerpAPIQuotaError on 429.
    """
    api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not api_key:
        logger.debug("SERPAPI_API_KEY not set, skipping SerpAPI search")
        return None

    _rate_limit()

    params: dict = {
        "engine": _SERPAPI_ENGINE,
        "api_key": api_key,
        "departure_id": origin.upper(),
        "arrival_id": dest.upper(),
        "outbound_date": date.isoformat(),
        "type": 2,  # one-way
        "travel_class": _CABIN_MAP.get(cabin.lower(), 3),
        "currency": "USD",
        "hl": "en",
        "deep_search": "true",
    }

    if oneworld_only:
        params["include_airlines"] = "ONEWORLD"

    if max_stops is not None and max_stops in _STOPS_MAP:
        params["stops"] = _STOPS_MAP[max_stops]

    try:
        resp = requests.get(_SERPAPI_BASE_URL, params=params, timeout=_SERPAPI_TIMEOUT_S)
    except requests.Timeout:
        logger.warning("SerpAPI timeout for %s-%s", origin, dest)
        return None
    except requests.RequestException as exc:
        logger.warning("SerpAPI network error for %s-%s: %s", origin, dest, exc)
        return None

    if resp.status_code == 401:
        raise SerpAPIAuthError("Invalid or missing SERPAPI_API_KEY")
    if resp.status_code == 429:
        raise SerpAPIQuotaError("Monthly SerpAPI search quota exceeded")
    if resp.status_code >= 400:
        logger.warning("SerpAPI HTTP %d for %s-%s", resp.status_code, origin, dest)
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.warning("SerpAPI returned non-JSON for %s-%s", origin, dest)
        return None

    # Check for API-level error in response body
    if data.get("error"):
        logger.warning("SerpAPI error for %s-%s: %s", origin, dest, data["error"])
        return None

    return _parse_serpapi_response(data, origin, dest, date, cabin)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_serpapi_response(
    data: dict,
    origin: str,
    dest: str,
    date: Date,
    cabin: str,
) -> Optional[FlightPrice]:
    """Extract cheapest flight from SerpAPI response."""
    best = data.get("best_flights", [])
    other = data.get("other_flights", [])
    all_options = best + other

    if not all_options:
        logger.info("SerpAPI: no flights for %s-%s on %s", origin, dest, date)
        return None

    # Find cheapest option with a valid price
    cheapest = None
    for option in all_options:
        price = option.get("price")
        if price is None:
            continue
        if cheapest is None or price < cheapest.get("price", float("inf")):
            cheapest = option

    if cheapest is None:
        logger.info("SerpAPI: no priced flights for %s-%s on %s", origin, dest, date)
        return None

    # Extract carrier from first flight leg
    flights = cheapest.get("flights", [])
    if not flights:
        return None

    first_leg = flights[0]
    airline_name = first_leg.get("airline", "")
    flight_number = first_leg.get("flight_number", "")
    carrier_code = _extract_carrier_iata_from_serpapi(airline_name)

    # Stops = number of layovers (0 = nonstop)
    layovers = cheapest.get("layovers", [])
    stops = len(layovers)

    # Duration
    duration_minutes = cheapest.get("total_duration")

    logger.info(
        "SerpAPI found %s-%s: %s $%.0f (%s)",
        origin, dest, carrier_code, cheapest["price"],
        "nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}",
    )

    return FlightPrice(
        origin=origin.upper(),
        dest=dest.upper(),
        carrier=carrier_code,
        price_usd=float(cheapest["price"]),
        cabin=cabin,
        date=date,
        source="serpapi",
        stops=stops,
        flight_number=flight_number or None,
        duration_minutes=duration_minutes,
        airline_name=airline_name or None,
    )


def _extract_carrier_iata_from_serpapi(airline_name: str) -> str:
    """Map airline name from SerpAPI to IATA code."""
    text = airline_name.lower().strip()
    for name, code in _CARRIER_IATA.items():
        if name in text:
            return code
    return airline_name[:2].upper() if len(airline_name) >= 2 else "??"
