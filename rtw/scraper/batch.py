"""Batch scraping operations for RTW itineraries.

Searches prices and availability for all segments in an itinerary,
with graceful degradation when scrapers fail.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from rtw.models import Itinerary
from rtw.scraper.cache import ScrapeCache
from rtw.scraper.expertflyer import ExpertFlyerScraper
from rtw.scraper.google_flights import FlightPrice, search_fast_flights

logger = logging.getLogger(__name__)


async def search_itinerary_prices(
    itinerary: Itinerary,
    cache: Optional[ScrapeCache] = None,
) -> list[Optional[FlightPrice]]:
    """Search prices for all flown segments in an itinerary.

    Args:
        itinerary: The RTW itinerary to price.
        cache: Optional ScrapeCache for caching results.

    Returns:
        List of FlightPrice (or None) for each segment. Surface segments
        get None. Failed searches get None. Never raises.
    """
    if cache is None:
        cache = ScrapeCache()

    results: list[Optional[FlightPrice]] = []

    for seg in itinerary.segments:
        if seg.is_surface or seg.date is None:
            results.append(None)
            continue

        # Check cache first
        cache_key = (
            f"price_{seg.from_airport}_{seg.to_airport}_{seg.date}_{itinerary.ticket.cabin.value}"
        )
        cached = cache.get(cache_key)
        if cached is not None:
            try:
                results.append(FlightPrice(**cached))
                continue
            except Exception:
                pass  # Invalid cache entry, re-fetch

        # Try searching
        try:
            price = search_fast_flights(
                origin=seg.from_airport,
                dest=seg.to_airport,
                date=seg.date,
                cabin=itinerary.ticket.cabin.value,
            )
            if price is not None:
                # Cache the result
                from dataclasses import asdict

                cache.set(cache_key, asdict(price))
            results.append(price)
        except Exception as exc:
            logger.warning(
                "Price search failed for %s-%s: %s",
                seg.from_airport,
                seg.to_airport,
                exc,
            )
            results.append(None)

    return results


async def check_itinerary_availability(
    itinerary: Itinerary,
    booking_class: str = "D",
) -> list[Optional[dict]]:
    """Check award availability for all flown segments.

    Args:
        itinerary: The RTW itinerary to check.
        booking_class: Booking class to check (default "D" for business award).

    Returns:
        List of availability dicts (or None) for each segment.
        Surface segments and segments without carriers get None. Never raises.
    """
    scraper = ExpertFlyerScraper()

    if not scraper.credentials_available():
        logger.info("ExpertFlyer credentials not available - returning empty results")
        return [None] * len(itinerary.segments)

    results: list[Optional[dict]] = []

    for seg in itinerary.segments:
        if seg.is_surface or seg.carrier is None or seg.date is None:
            results.append(None)
            continue

        try:
            avail = await scraper.check_availability(
                origin=seg.from_airport,
                dest=seg.to_airport,
                date=seg.date,
                carrier=seg.carrier,
                booking_class=booking_class,
            )
            results.append(avail)
        except Exception as exc:
            logger.warning(
                "Availability check failed for %s %s-%s: %s",
                seg.carrier,
                seg.from_airport,
                seg.to_airport,
                exc,
            )
            results.append(None)

    return results


def search_with_fallback(
    itinerary: Itinerary,
    cache: Optional[ScrapeCache] = None,
) -> list[Optional[FlightPrice]]:
    """Synchronous wrapper for search_itinerary_prices.

    Runs the async search in an event loop. Safe to call from sync code.
    Returns empty/None results on any failure - never crashes.

    Args:
        itinerary: The RTW itinerary to price.
        cache: Optional ScrapeCache for caching results.

    Returns:
        List of FlightPrice (or None) for each segment.
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # Already in an async context - can't nest event loops
            # Return empty results rather than crash
            logger.warning("Cannot run async search from within running event loop")
            return [None] * len(itinerary.segments)

        return asyncio.run(search_itinerary_prices(itinerary, cache))

    except Exception as exc:
        logger.warning("search_with_fallback failed: %s", exc)
        return [None] * len(itinerary.segments)
