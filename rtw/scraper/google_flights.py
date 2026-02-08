"""Google Flights price scraping via fast-flights library and Playwright fallback.

All functions degrade gracefully to None when services are unavailable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date as Date
from typing import Optional

logger = logging.getLogger(__name__)

# Rate limiting: minimum seconds between scrape calls
_RATE_LIMIT_SECONDS = 2.0
_last_call_time: float = 0.0


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
        from fast_flights import FlightData, Passengers, create_filter, get_flights
    except ImportError:
        logger.info("fast-flights library not available")
        return None

    _rate_limit()

    try:
        # Map cabin names to fast-flights enum values
        cabin_map = {
            "economy": 1,
            "business": 3,
            "first": 4,
        }
        cabin_code = cabin_map.get(cabin.lower(), 3)

        flight_filter = create_filter(
            flight_data=[
                FlightData(date=date.strftime("%Y-%m-%d"), from_airport=origin, to_airport=dest)
            ],
            trip="one-way",
            seat=cabin_code,
            passengers=Passengers(adults=1),
        )
        result = get_flights(flight_filter)

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
        logger.warning("fast-flights search failed for %s-%s: %s", origin, dest, exc)
        return None


async def search_playwright(
    origin: str,
    dest: str,
    date: Date,
    cabin: str = "business",
    browser=None,
) -> Optional[FlightPrice]:
    """Fallback: scrape Google Flights via Playwright.

    This is a stub implementation. Full Playwright scraping would navigate
    to Google Flights, fill in the search form, and extract prices.

    Args:
        origin: 3-letter IATA airport code.
        dest: 3-letter IATA airport code.
        date: Flight date.
        cabin: Cabin class.
        browser: Playwright browser instance (from BrowserManager).

    Returns:
        FlightPrice or None if scraping failed.
    """
    if browser is None:
        logger.info("No browser provided for Playwright search")
        return None

    _rate_limit()

    try:
        page = await browser.new_page()
        try:
            # Build Google Flights URL
            url = (
                f"https://www.google.com/travel/flights?"
                f"q=flights+from+{origin}+to+{dest}+on+{date.isoformat()}"
            )
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # NOTE: Full implementation would parse the results page here.
            # This is a P2 stub - Google Flights DOM parsing is fragile and
            # changes frequently. For now, we log and return None.
            logger.info(
                "Playwright Google Flights stub: would scrape %s-%s on %s",
                origin,
                dest,
                date,
            )
            return None

        finally:
            await page.close()

    except Exception as exc:
        logger.warning("Playwright search failed for %s-%s: %s", origin, dest, exc)
        return None


async def search(
    origin: str,
    dest: str,
    date: Date,
    cabin: str = "business",
) -> Optional[FlightPrice]:
    """Search for flight prices, trying fast-flights first then Playwright.

    Args:
        origin: 3-letter IATA airport code.
        dest: 3-letter IATA airport code.
        date: Flight date.
        cabin: Cabin class.

    Returns:
        FlightPrice or None if all methods failed.
    """
    # Try fast-flights first (sync call)
    result = search_fast_flights(origin, dest, date, cabin)
    if result is not None:
        return result

    # Try Playwright fallback
    try:
        from rtw.scraper import BrowserManager

        if not BrowserManager.available():
            logger.info("Playwright not available, skipping browser fallback")
            return None

        async with BrowserManager() as browser:
            return await search_playwright(origin, dest, date, cabin, browser)

    except Exception as exc:
        logger.warning("All search methods failed for %s-%s: %s", origin, dest, exc)
        return None
