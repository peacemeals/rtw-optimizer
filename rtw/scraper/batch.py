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
from rtw.scraper.google_flights import FlightPrice, SearchBackend, search_fast_flights

logger = logging.getLogger(__name__)


async def search_itinerary_prices(
    itinerary: Itinerary,
    cache: Optional[ScrapeCache] = None,
    backend: SearchBackend = SearchBackend.AUTO,
) -> list[Optional[FlightPrice]]:
    """Search prices for all flown segments in an itinerary.

    Args:
        itinerary: The RTW itinerary to price.
        cache: Optional ScrapeCache for caching results.
        backend: Which search backend to use.

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

        # Try searching with cascade
        try:
            price = _search_segment_price(
                seg.from_airport, seg.to_airport, seg.date,
                itinerary.ticket.cabin.value, backend,
            )
            if price is not None:
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


def _search_segment_price(origin, dest, seg_date, cabin, backend):
    """Search a single segment using the configured backend."""
    if backend == SearchBackend.AUTO:
        search_fns = _auto_price_cascade()
    elif backend == SearchBackend.SERPAPI:
        search_fns = [("serpapi", _try_serpapi_price)]
    elif backend == SearchBackend.FAST_FLIGHTS:
        search_fns = [("fast-flights", _try_fast_flights_price)]
    elif backend == SearchBackend.PLAYWRIGHT:
        search_fns = [("playwright", _try_playwright_price)]
    else:
        search_fns = _auto_price_cascade()

    for name, fn in search_fns:
        try:
            result = fn(origin, dest, seg_date, cabin)
            if result is not None:
                return result
        except Exception as exc:
            if backend != SearchBackend.AUTO:
                raise
            logger.debug("Batch cascade %s failed for %s-%s: %s", name, origin, dest, exc)

    return None


def _auto_price_cascade():
    """Build cascade for batch pricing: serpapi -> fast-flights (no Playwright — too slow)."""
    fns = []
    from rtw.scraper.serpapi_flights import serpapi_available
    if serpapi_available():
        fns.append(("serpapi", _try_serpapi_price))
    fns.append(("fast-flights", _try_fast_flights_price))
    return fns


def _try_serpapi_price(origin, dest, seg_date, cabin):
    from rtw.scraper.serpapi_flights import search_serpapi
    return search_serpapi(origin=origin, dest=dest, date=seg_date, cabin=cabin)


def _try_fast_flights_price(origin, dest, seg_date, cabin):
    return search_fast_flights(origin, dest, seg_date, cabin)


def _try_playwright_price(origin, dest, seg_date, cabin):
    from rtw.scraper.google_flights import search_playwright_sync
    return search_playwright_sync(origin, dest, seg_date, cabin)


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
    backend: SearchBackend = SearchBackend.AUTO,
) -> list[Optional[FlightPrice]]:
    """Synchronous wrapper for search_itinerary_prices.

    Runs the async search in an event loop. Safe to call from sync code.
    Returns empty/None results on any failure - never crashes.

    Args:
        itinerary: The RTW itinerary to price.
        cache: Optional ScrapeCache for caching results.
        backend: Which search backend to use.

    Returns:
        List of FlightPrice (or None) for each segment.
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            logger.warning("Cannot run async search from within running event loop")
            return [None] * len(itinerary.segments)

        return asyncio.run(search_itinerary_prices(itinerary, cache, backend))

    except Exception as exc:
        logger.warning("search_with_fallback failed: %s", exc)
        return [None] * len(itinerary.segments)
