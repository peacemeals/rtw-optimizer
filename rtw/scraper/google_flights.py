"""Google Flights price scraping via Playwright (primary) and fast-flights (fallback).

All functions degrade gracefully to None when services are unavailable.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date as Date
from typing import Optional

logger = logging.getLogger(__name__)

# Rate limiting: minimum seconds between scrape calls
_RATE_LIMIT_SECONDS = 2.0
_last_call_time: float = 0.0

# Oneworld carriers for filtering
_ONEWORLD_CARRIERS = {
    "american", "british airways", "cathay pacific", "finnair", "iberia",
    "japan airlines", "jal", "malaysia airlines", "qantas", "qatar airways",
    "royal air maroc", "royal jordanian", "srilankan", "alaska",
    "fiji airways", "oman air", "s7 airlines",
    # IATA codes as fallback
    "aa", "ba", "cx", "ay", "ib", "jl", "mh", "qf", "qr", "at", "rj",
    "ul", "as", "fj", "wy", "s7",
}

# Carrier name -> IATA code mapping
_CARRIER_IATA = {
    "american": "AA", "british airways": "BA", "cathay pacific": "CX",
    "finnair": "AY", "iberia": "IB", "japan airlines": "JL", "jal": "JL",
    "malaysia airlines": "MH", "qantas": "QF", "qatar airways": "QR",
    "royal air maroc": "AT", "royal jordanian": "RJ", "srilankan": "UL",
    "alaska": "AS", "fiji airways": "FJ", "oman air": "WY", "s7 airlines": "S7",
}


@dataclass
class FlightPrice:
    """Price result from a flight search."""

    origin: str
    dest: str
    carrier: str
    price_usd: float
    cabin: str  # "economy", "business", "first"
    date: Optional[Date] = None
    source: str = "google_flights"  # "fast_flights" or "playwright"


def _rate_limit() -> None:
    """Enforce minimum delay between scrape calls."""
    global _last_call_time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_call_time = time.time()


def search_fast_flights(
    origin: str,
    dest: str,
    date: Date,
    cabin: str = "business",
) -> Optional[FlightPrice]:
    """Search Google Flights using the fast-flights library.

    Args:
        origin: 3-letter IATA airport code.
        dest: 3-letter IATA airport code.
        date: Flight date.
        cabin: Cabin class (economy, business, first).

    Returns:
        FlightPrice or None if search failed.
    """
    try:
        from fast_flights import FlightData, Passengers, get_flights
    except ImportError:
        logger.info("fast-flights library not available")
        return None

    _rate_limit()

    try:
        # Map cabin names to fast-flights seat literals
        cabin_map = {
            "economy": "economy",
            "premium_economy": "premium-economy",
            "business": "business",
            "first": "first",
        }
        seat_label = cabin_map.get(cabin.lower(), "business")

        result = get_flights(
            flight_data=[
                FlightData(date=date.strftime("%Y-%m-%d"), from_airport=origin, to_airport=dest)
            ],
            trip="one-way",
            seat=seat_label,
            passengers=Passengers(adults=1),
        )

        if not result or not result.flights:
            logger.info("No fast-flights results for %s-%s on %s", origin, dest, date)
            return None

        # Take the cheapest result
        best = min(result.flights, key=lambda f: f.price or float("inf"))
        if best.price is None:
            return None

        return FlightPrice(
            origin=origin.upper(),
            dest=dest.upper(),
            carrier=best.name or "Unknown",
            price_usd=float(best.price),
            cabin=cabin,
            date=date,
            source="fast_flights",
        )

    except Exception as exc:
        # Truncate consent wall spam from error message
        msg = str(exc).split("\n")[0][:100]
        logger.debug("fast-flights failed for %s-%s: %s", origin, dest, msg)
        return None


def _extract_carrier_iata(carrier_text: str) -> str:
    """Extract IATA code from carrier name text."""
    text = carrier_text.lower().strip()
    for name, code in _CARRIER_IATA.items():
        if name in text:
            return code
    return carrier_text[:2].upper() if len(carrier_text) >= 2 else "??"


def _is_oneworld(carrier_text: str) -> bool:
    """Check if any oneworld carrier appears in the text."""
    text = carrier_text.lower()
    return any(ow in text for ow in _ONEWORLD_CARRIERS)


def _parse_price(text: str) -> Optional[float]:
    """Extract USD price from text like '$5,026'."""
    m = re.search(r"\$([\d,]+)", text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def search_playwright_sync(
    origin: str,
    dest: str,
    date: Date,
    cabin: str = "business",
    oneworld_only: bool = True,
) -> Optional[FlightPrice]:
    """Scrape Google Flights via Playwright (sync).

    Returns the cheapest flight found, optionally filtered to oneworld carriers.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("Playwright not installed")
        return None

    _rate_limit()

    cabin_query = {"business": "business+class", "first": "first+class"}.get(
        cabin.lower(), ""
    )
    url = (
        f"https://www.google.com/travel/flights?"
        f"q=flights+from+{origin}+to+{dest}+on+{date.isoformat()}"
        f"+{cabin_query}&curr=USD"
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(url, timeout=30000)

                # Dismiss cookie consent if present
                try:
                    btn = page.locator("button:has-text('Accept all')").first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

                # Wait for flight results to render
                page.wait_for_timeout(4000)

                results = page.locator("li.pIav2d").all()
                if not results:
                    logger.info("No flight results found for %s-%s on %s", origin, dest, date)
                    return None

                best: Optional[FlightPrice] = None

                for result in results:
                    text = result.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if len(lines) < 4:
                        continue

                    price = _parse_price(text)
                    if price is None:
                        continue

                    # Lines layout: time, –, time, carrier(s), duration, route, stops, price
                    carrier_text = lines[3] if len(lines) > 3 else ""

                    if oneworld_only and not _is_oneworld(carrier_text):
                        continue

                    carrier_code = _extract_carrier_iata(carrier_text)

                    if best is None or price < best.price_usd:
                        best = FlightPrice(
                            origin=origin.upper(),
                            dest=dest.upper(),
                            carrier=carrier_code,
                            price_usd=price,
                            cabin=cabin,
                            date=date,
                            source="playwright",
                        )

                if best:
                    logger.info(
                        "Playwright found %s-%s: %s $%.0f",
                        origin, dest, best.carrier, best.price_usd,
                    )
                else:
                    logger.info("No %sflights for %s-%s on %s",
                                "oneworld " if oneworld_only else "", origin, dest, date)

                return best

            finally:
                page.close()
                browser.close()

    except Exception as exc:
        logger.warning("Playwright search failed for %s-%s: %s", origin, dest, exc)
        return None
