"""Tests for batch scraping operations."""

from datetime import date
from unittest.mock import patch

import pytest

from rtw.models import CabinClass, Itinerary, Segment, SegmentType, Ticket, TicketType
from rtw.scraper.batch import (
    check_itinerary_availability,
    search_itinerary_prices,
    search_with_fallback,
)
from rtw.scraper.cache import ScrapeCache


def _make_itinerary() -> Itinerary:
    """Create a simple test itinerary."""
    return Itinerary(
        ticket=Ticket(
            type=TicketType.DONE3,
            cabin=CabinClass.BUSINESS,
            origin="LHR",
        ),
        segments=[
            Segment(
                **{
                    "from": "LHR",
                    "to": "DOH",
                    "carrier": "QR",
                    "date": date(2025, 6, 1),
                    "type": SegmentType.STOPOVER,
                }
            ),
            Segment(
                **{
                    "from": "DOH",
                    "to": "NRT",
                    "carrier": "JL",
                    "date": date(2025, 6, 5),
                    "type": SegmentType.STOPOVER,
                }
            ),
            Segment(
                **{
                    "from": "NRT",
                    "to": "SYD",
                    "type": SegmentType.SURFACE,
                }
            ),
            Segment(
                **{
                    "from": "SYD",
                    "to": "LHR",
                    "carrier": "QF",
                    "date": date(2025, 6, 20),
                    "type": SegmentType.FINAL,
                }
            ),
        ],
    )


class TestSearchItineraryPrices:
    """Test batch price searching."""

    @pytest.mark.asyncio
    async def test_graceful_failure_all_segments(self, tmp_path):
        """Returns list of Nones when all searches fail."""
        itin = _make_itinerary()
        cache = ScrapeCache(cache_dir=tmp_path)

        with patch("rtw.scraper.batch.search_fast_flights", return_value=None):
            results = await search_itinerary_prices(itin, cache)

        assert len(results) == len(itin.segments)
        # All should be None (searches failed or surface segments)
        for r in results:
            assert r is None

    @pytest.mark.asyncio
    async def test_surface_segments_get_none(self, tmp_path):
        """Surface segments always return None."""
        itin = _make_itinerary()
        cache = ScrapeCache(cache_dir=tmp_path)

        with patch("rtw.scraper.batch.search_fast_flights", return_value=None):
            results = await search_itinerary_prices(itin, cache)

        # Segment index 2 is surface
        assert results[2] is None

    @pytest.mark.asyncio
    async def test_uses_cache(self, tmp_path):
        """Cached results are returned without re-searching."""
        itin = _make_itinerary()
        cache = ScrapeCache(cache_dir=tmp_path)

        # Pre-populate cache for first segment
        seg = itin.segments[0]
        cache_key = (
            f"price_{seg.from_airport}_{seg.to_airport}_{seg.date}_{itin.ticket.cabin.value}"
        )
        cache.set(
            cache_key,
            {
                "origin": "LHR",
                "dest": "DOH",
                "carrier": "QR",
                "price_usd": 3000.0,
                "cabin": "business",
                "source": "fast_flights",
            },
        )

        with patch("rtw.scraper.batch.search_fast_flights", return_value=None):
            results = await search_itinerary_prices(itin, cache)

        # First segment should come from cache
        assert results[0] is not None
        assert results[0].price_usd == 3000.0
        assert results[0].origin == "LHR"

    @pytest.mark.asyncio
    async def test_never_crashes(self, tmp_path):
        """Even with exceptions in search, never crashes."""
        itin = _make_itinerary()
        cache = ScrapeCache(cache_dir=tmp_path)

        with patch(
            "rtw.scraper.batch.search_fast_flights",
            side_effect=RuntimeError("Unexpected error"),
        ):
            results = await search_itinerary_prices(itin, cache)

        assert len(results) == len(itin.segments)
        # All should be None due to failures
        for r in results:
            assert r is None


class TestCheckItineraryAvailability:
    """Test batch availability checking."""

    @pytest.mark.asyncio
    async def test_returns_nones_without_credentials(self):
        """Returns all Nones when ExpertFlyer credentials are not available."""
        itin = _make_itinerary()

        with patch("rtw.scraper.batch.ExpertFlyerScraper") as MockScraper:
            instance = MockScraper.return_value
            instance.credentials_available.return_value = False

            results = await check_itinerary_availability(itin)

        assert len(results) == len(itin.segments)
        for r in results:
            assert r is None


class TestSearchWithFallback:
    """Test synchronous wrapper."""

    def test_returns_list_of_nones_on_total_failure(self, tmp_path):
        """search_with_fallback returns Nones on complete failure."""
        itin = _make_itinerary()
        cache = ScrapeCache(cache_dir=tmp_path)

        with patch("rtw.scraper.batch.search_fast_flights", return_value=None):
            results = search_with_fallback(itin, cache)

        assert len(results) == len(itin.segments)
        for r in results:
            assert r is None

    def test_never_crashes(self, tmp_path):
        """search_with_fallback never crashes, even on unexpected errors."""
        itin = _make_itinerary()
        cache = ScrapeCache(cache_dir=tmp_path)

        with patch(
            "rtw.scraper.batch.search_fast_flights",
            side_effect=RuntimeError("Total failure"),
        ):
            results = search_with_fallback(itin, cache)

        assert isinstance(results, list)
        assert len(results) == len(itin.segments)

    def test_empty_itinerary(self):
        """Handles itinerary with minimal segments."""
        itin = Itinerary(
            ticket=Ticket(
                type=TicketType.DONE3,
                cabin=CabinClass.BUSINESS,
                origin="LHR",
            ),
            segments=[
                Segment(
                    **{
                        "from": "LHR",
                        "to": "DOH",
                        "carrier": "QR",
                        "date": date(2025, 6, 1),
                        "type": SegmentType.STOPOVER,
                    }
                ),
            ],
        )

        with patch("rtw.scraper.batch.search_fast_flights", return_value=None):
            results = search_with_fallback(itin)

        assert len(results) == 1
        assert results[0] is None
