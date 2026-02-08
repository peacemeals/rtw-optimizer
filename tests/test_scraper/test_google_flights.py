"""Tests for Google Flights scraper module."""

from datetime import date
from unittest.mock import patch

import pytest

from rtw.scraper.google_flights import FlightPrice, search_fast_flights, search


class TestFlightPrice:
    """Test the FlightPrice dataclass."""

    def test_create_flight_price(self):
        """FlightPrice can be created with required fields."""
        fp = FlightPrice(
            origin="LHR",
            dest="NRT",
            carrier="JL",
            price_usd=2500.00,
            cabin="business",
        )
        assert fp.origin == "LHR"
        assert fp.dest == "NRT"
        assert fp.carrier == "JL"
        assert fp.price_usd == 2500.00
        assert fp.cabin == "business"
        assert fp.source == "google_flights"
        assert fp.date is None

    def test_create_with_all_fields(self):
        """FlightPrice with all optional fields."""
        fp = FlightPrice(
            origin="LAX",
            dest="SYD",
            carrier="QF",
            price_usd=4000.00,
            cabin="first",
            date=date(2025, 6, 15),
            source="fast_flights",
        )
        assert fp.date == date(2025, 6, 15)
        assert fp.source == "fast_flights"


class TestSearchFastFlights:
    """Test search_fast_flights graceful degradation."""

    def test_returns_none_when_library_unavailable(self):
        """Returns None when fast-flights library is not importable."""
        with patch.dict("sys.modules", {"fast_flights": None}):
            # When the import inside search_fast_flights tries 'from fast_flights import ...',
            # it will get ImportError because we set the module to None
            result = search_fast_flights("LHR", "NRT", date(2025, 6, 15), "business")
            # The function catches ImportError and returns None
            assert result is None

    def test_returns_none_on_exception(self):
        """Returns None on any exception during search."""
        # Mock fast_flights to raise an exception
        import types

        mock_module = types.ModuleType("fast_flights")
        mock_module.FlightData = type("FlightData", (), {"__init__": lambda self, **kw: None})
        mock_module.Passengers = type("Passengers", (), {"__init__": lambda self, **kw: None})
        mock_module.create_filter = lambda **kw: None
        mock_module.get_flights = lambda f: (_ for _ in ()).throw(RuntimeError("API error"))

        with patch.dict("sys.modules", {"fast_flights": mock_module}):
            result = search_fast_flights("LHR", "NRT", date(2025, 6, 15))
            assert result is None


class TestSearch:
    """Test combined search function."""

    @pytest.mark.asyncio
    async def test_search_returns_none_gracefully(self):
        """Combined search returns None when all methods fail."""
        # Patch fast-flights to fail, and BrowserManager to not be available
        with (
            patch("rtw.scraper.google_flights.search_fast_flights", return_value=None),
            patch("rtw.scraper.BrowserManager") as mock_bm,
        ):
            mock_bm.available.return_value = False
            result = await search("LHR", "NRT", date(2025, 6, 15))
            assert result is None

    @pytest.mark.asyncio
    async def test_search_returns_fast_flights_result_first(self):
        """Combined search returns fast-flights result when available."""
        expected = FlightPrice(
            origin="LHR",
            dest="NRT",
            carrier="JL",
            price_usd=2500.00,
            cabin="business",
            source="fast_flights",
        )
        with patch("rtw.scraper.google_flights.search_fast_flights", return_value=expected):
            result = await search("LHR", "NRT", date(2025, 6, 15))
            assert result is not None
            assert result.price_usd == 2500.00
            assert result.source == "fast_flights"


class TestRateLimiting:
    """Test rate limiting infrastructure."""

    def test_rate_limit_constant_defined(self):
        """Rate limit constant is set to 2 seconds."""
        from rtw.scraper.google_flights import _RATE_LIMIT_SECONDS

        assert _RATE_LIMIT_SECONDS == 2.0

    def test_rate_limit_function_exists(self):
        """Rate limit function is importable."""
        from rtw.scraper.google_flights import _rate_limit

        assert callable(_rate_limit)
