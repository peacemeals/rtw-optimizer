"""Tests for Google Flights scraper module."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from rtw.scraper.google_flights import (
    FlightPrice,
    ScrapeError,
    ScrapeFailureReason,
    _CONSENT_SELECTORS,
    _MAX_ATTEMPTS,
    _RETRY_BACKOFF_S,
    _SELECTORS,
    _dismiss_consent,
    _expand_all_results,
    _extract_carrier_iata,
    _is_oneworld,
    _parse_flight_card,
    _parse_price,
    _parse_stops,
    search_fast_flights,
    search_playwright_sync,
)


# ---------------------------------------------------------------------------
# Existing tests (fixed import, no TestSearch)
# ---------------------------------------------------------------------------


class TestFlightPrice:
    """Test the FlightPrice dataclass."""

    def test_create_flight_price(self):
        fp = FlightPrice(
            origin="LHR", dest="NRT", carrier="JL",
            price_usd=2500.00, cabin="business",
        )
        assert fp.origin == "LHR"
        assert fp.dest == "NRT"
        assert fp.carrier == "JL"
        assert fp.price_usd == 2500.00
        assert fp.cabin == "business"
        assert fp.source == "google_flights"
        assert fp.date is None
        assert fp.stops is None

    def test_create_with_all_fields(self):
        fp = FlightPrice(
            origin="LAX", dest="SYD", carrier="QF",
            price_usd=4000.00, cabin="first",
            date=date(2025, 6, 15), source="fast_flights",
        )
        assert fp.date == date(2025, 6, 15)
        assert fp.source == "fast_flights"

    def test_flight_price_with_stops(self):
        fp = FlightPrice(
            origin="DOH", dest="SYD", carrier="QR",
            price_usd=5026.0, cabin="business", stops=0,
        )
        assert fp.stops == 0

    def test_flight_price_stops_default_none(self):
        fp = FlightPrice(
            origin="DOH", dest="SYD", carrier="QR",
            price_usd=5026.0, cabin="business",
        )
        assert fp.stops is None

    def test_flight_price_stops_backward_compat(self):
        """Existing positional keyword creation still works."""
        fp = FlightPrice(
            origin="LHR", dest="NRT", carrier="JL",
            price_usd=2500.0, cabin="business",
            date=date(2025, 6, 15), source="playwright",
        )
        assert fp.stops is None
        assert fp.source == "playwright"


class TestSearchFastFlights:
    """Test search_fast_flights graceful degradation."""

    def test_returns_none_when_library_unavailable(self):
        with patch.dict("sys.modules", {"fast_flights": None}):
            result = search_fast_flights("LHR", "NRT", date(2025, 6, 15), "business")
            assert result is None

    def test_returns_none_on_exception(self):
        import types
        mock_module = types.ModuleType("fast_flights")
        mock_module.FlightData = type("FlightData", (), {"__init__": lambda self, **kw: None})
        mock_module.Passengers = type("Passengers", (), {"__init__": lambda self, **kw: None})
        mock_module.create_filter = lambda **kw: None
        mock_module.get_flights = lambda f: (_ for _ in ()).throw(RuntimeError("API error"))

        with patch.dict("sys.modules", {"fast_flights": mock_module}):
            result = search_fast_flights("LHR", "NRT", date(2025, 6, 15))
            assert result is None


class TestRateLimiting:
    """Test rate limiting infrastructure."""

    def test_rate_limit_constant_defined(self):
        from rtw.scraper.google_flights import _RATE_LIMIT_SECONDS
        assert _RATE_LIMIT_SECONDS == 2.0

    def test_rate_limit_function_exists(self):
        from rtw.scraper.google_flights import _rate_limit
        assert callable(_rate_limit)


# ---------------------------------------------------------------------------
# New tests for scraper robustness
# ---------------------------------------------------------------------------


class TestParsePrice:
    """Test _parse_price pure function."""

    def test_parse_price_simple(self):
        assert _parse_price("$1,234") == 1234.0

    def test_parse_price_no_comma(self):
        assert _parse_price("$500") == 500.0

    def test_parse_price_large(self):
        assert _parse_price("$12,345") == 12345.0

    def test_parse_price_in_text(self):
        assert _parse_price("From $5,026 round trip") == 5026.0

    def test_parse_price_no_dollar(self):
        assert _parse_price("5026 USD") is None

    def test_parse_price_empty(self):
        assert _parse_price("") is None


class TestParseStops:
    """Test _parse_stops with mocked card locators."""

    def _make_card(self, stops_text, selector_works=True):
        card = MagicMock()
        if selector_works:
            stops_el = MagicMock()
            stops_el.inner_text.return_value = stops_text
            card.locator.return_value.first = stops_el
        else:
            card.locator.return_value.first.inner_text.side_effect = Exception("no element")
            card.inner_text.return_value = f"Airline\n10:00\n$5,000\n{stops_text}"
        return card

    def test_parse_stops_nonstop(self):
        assert _parse_stops(self._make_card("Nonstop")) == 0

    def test_parse_stops_one_stop(self):
        assert _parse_stops(self._make_card("1 stop")) == 1

    def test_parse_stops_two_stops(self):
        assert _parse_stops(self._make_card("2 stops")) == 2

    def test_parse_stops_three_stops(self):
        assert _parse_stops(self._make_card("3 stops")) == 3

    def test_parse_stops_nonstop_case_insensitive(self):
        assert _parse_stops(self._make_card("NONSTOP")) == 0
        assert _parse_stops(self._make_card("NonStop")) == 0

    def test_parse_stops_unparseable(self):
        assert _parse_stops(self._make_card("Some random text")) is None

    def test_parse_stops_empty_text(self):
        assert _parse_stops(self._make_card("")) is None

    def test_parse_stops_selector_fails_regex_fallback(self):
        card = self._make_card("1 stop", selector_works=False)
        assert _parse_stops(card) == 1


class TestParseFlightCard:
    """Test _parse_flight_card with mocked card elements."""

    def _make_card(self, lines, stops_text="Nonstop"):
        card = MagicMock()
        card.inner_text.return_value = "\n".join(lines)
        # Mock stops locator
        stops_el = MagicMock()
        stops_el.inner_text.return_value = stops_text
        card.locator.return_value.first = stops_el
        return card

    def test_parse_card_complete(self):
        lines = ["10:00 AM", "-", "4:00 PM", "Qatar Airways", "8h 00m", "DOH-NRT", "Nonstop", "$5,026"]
        result = _parse_flight_card(self._make_card(lines), "DOH", "NRT", date(2026, 9, 1), "business")
        assert result is not None
        assert result["price"] == 5026.0
        assert result["carrier_text"] == "Qatar Airways"
        assert result["carrier_code"] == "QR"
        assert result["stops"] == 0

    def test_parse_card_no_price(self):
        lines = ["10:00 AM", "-", "4:00 PM", "Qatar Airways", "8h 00m", "DOH-NRT", "Nonstop"]
        result = _parse_flight_card(self._make_card(lines), "DOH", "NRT", date(2026, 9, 1), "business")
        assert result is None

    def test_parse_card_inner_text_exception(self):
        card = MagicMock()
        card.inner_text.side_effect = Exception("detached")
        result = _parse_flight_card(card, "DOH", "NRT", date(2026, 9, 1), "business")
        assert result is None

    def test_parse_card_short_lines(self):
        lines = ["$5,026", "Something"]
        result = _parse_flight_card(self._make_card(lines, ""), "DOH", "NRT", date(2026, 9, 1), "business")
        # < 4 lines, returns None
        assert result is None

    def test_parse_card_four_lines_with_carrier(self):
        lines = ["10:00 AM", "-", "4:00 PM", "Japan Airlines", "$4,500"]
        result = _parse_flight_card(self._make_card(lines), "NRT", "LHR", date(2026, 9, 1), "business")
        assert result is not None
        assert result["carrier_text"] == "Japan Airlines"
        assert result["carrier_code"] == "JL"

    def test_parse_card_oneworld_carrier(self):
        lines = ["10:00 AM", "-", "4:00 PM", "Qatar Airways", "8h", "route", "Nonstop", "$5,026"]
        result = _parse_flight_card(self._make_card(lines), "DOH", "NRT", date(2026, 9, 1), "business")
        assert result is not None
        assert "Qatar Airways" in result["carrier_text"]


class TestDismissConsent:
    """Test _dismiss_consent with mocked page."""

    def test_dismiss_consent_accept_all(self):
        page = MagicMock()
        btn = MagicMock()
        btn.is_visible.return_value = True
        page.locator.return_value.first = btn
        assert _dismiss_consent(page) is True
        btn.click.assert_called_once()

    def test_dismiss_consent_no_dialog(self):
        page = MagicMock()
        btn = MagicMock()
        btn.is_visible.side_effect = Exception("not found")
        page.locator.return_value.first = btn
        assert _dismiss_consent(page) is False

    def test_dismiss_consent_click_exception(self):
        page = MagicMock()
        btn = MagicMock()
        btn.is_visible.return_value = True
        btn.click.side_effect = Exception("click failed")
        page.locator.return_value.first = btn
        # First selector's click fails, rest have is_visible fail
        call_count = [0]
        original_is_visible = btn.is_visible

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return True  # First selector visible
            raise Exception("not found")  # Rest not found

        btn.is_visible.side_effect = side_effect
        # Click fails on first, rest not visible — returns False
        assert _dismiss_consent(page) is False


class TestExpandAllResults:
    """Test _expand_all_results with mocked page."""

    def test_expand_clicks_show_more(self):
        page = MagicMock()
        btn = MagicMock()
        btn.wait_for.side_effect = [None, None, Exception("not found")]
        page.locator.return_value.first = btn
        page.locator.return_value.all.return_value = [MagicMock()] * 15
        count = _expand_all_results(page)
        assert btn.click.call_count == 2
        assert count == 15

    def test_expand_no_button(self):
        page = MagicMock()
        btn = MagicMock()
        btn.wait_for.side_effect = Exception("not found")
        page.locator.return_value.first = btn
        page.locator.return_value.all.return_value = [MagicMock()] * 8
        count = _expand_all_results(page)
        assert btn.click.call_count == 0
        assert count == 8

    def test_expand_max_clicks_cap(self):
        page = MagicMock()
        btn = MagicMock()
        btn.wait_for.return_value = None  # Always visible
        page.locator.return_value.first = btn
        page.locator.return_value.all.return_value = [MagicMock()] * 50
        count = _expand_all_results(page)
        assert btn.click.call_count == 5  # _MAX_EXPAND_CLICKS

    def test_expand_returns_card_count(self):
        page = MagicMock()
        btn = MagicMock()
        btn.wait_for.side_effect = Exception("not found")
        page.locator.return_value.first = btn
        cards = [MagicMock() for _ in range(12)]
        page.locator.return_value.all.return_value = cards
        count = _expand_all_results(page)
        assert count == 12

    def test_expand_button_click_exception(self):
        page = MagicMock()
        btn = MagicMock()
        btn.wait_for.return_value = None
        btn.click.side_effect = Exception("click failed")
        page.locator.return_value.first = btn
        page.locator.return_value.all.return_value = [MagicMock()] * 10
        count = _expand_all_results(page)
        # Stops after first failed click
        assert count == 10


class TestScrapeError:
    """Test ScrapeError and ScrapeFailureReason."""

    def test_scrape_error_is_exception(self):
        e = ScrapeError(ScrapeFailureReason.TIMEOUT, "timed out")
        assert isinstance(e, Exception)

    def test_scrape_error_reason(self):
        e = ScrapeError(ScrapeFailureReason.CONSENT_BLOCKED, "blocked")
        assert e.reason == ScrapeFailureReason.CONSENT_BLOCKED

    def test_scrape_error_route(self):
        e = ScrapeError(ScrapeFailureReason.TIMEOUT, "msg", route="LHR-NRT")
        assert e.route == "LHR-NRT"

    def test_scrape_error_str(self):
        e = ScrapeError(ScrapeFailureReason.TIMEOUT, "timed out", route="LHR-NRT")
        s = str(e)
        assert "timeout" in s
        assert "LHR-NRT" in s

    def test_scrape_failure_reason_enum_values(self):
        assert ScrapeFailureReason.TIMEOUT.value == "timeout"
        assert ScrapeFailureReason.CONSENT_BLOCKED.value == "consent_blocked"
        assert ScrapeFailureReason.NO_RESULTS.value == "no_results"
        assert ScrapeFailureReason.PARSE_ERROR.value == "parse_error"
        assert ScrapeFailureReason.BROWSER_ERROR.value == "browser_error"


class TestRetryLogic:
    """Test retry wrapper in search_playwright_sync."""

    @patch("rtw.scraper.google_flights._search_playwright_impl")
    @patch("rtw.scraper.google_flights.time.sleep")
    def test_retry_succeeds_on_second_attempt(self, mock_sleep, mock_impl):
        expected = FlightPrice(
            origin="LHR", dest="NRT", carrier="JL",
            price_usd=2500.0, cabin="business",
        )
        mock_impl.side_effect = [
            ScrapeError(ScrapeFailureReason.TIMEOUT, "timeout", "LHR-NRT"),
            expected,
        ]
        result = search_playwright_sync("LHR", "NRT", date(2026, 9, 1))
        assert result == expected
        assert mock_impl.call_count == 2

    @patch("rtw.scraper.google_flights._search_playwright_impl")
    @patch("rtw.scraper.google_flights.time.sleep")
    def test_retry_exhausted_returns_none(self, mock_sleep, mock_impl):
        mock_impl.side_effect = ScrapeError(
            ScrapeFailureReason.TIMEOUT, "timeout", "LHR-NRT"
        )
        result = search_playwright_sync("LHR", "NRT", date(2026, 9, 1))
        assert result is None
        assert mock_impl.call_count == _MAX_ATTEMPTS

    @patch("rtw.scraper.google_flights._search_playwright_impl")
    @patch("rtw.scraper.google_flights.time.sleep")
    def test_no_retry_on_consent_blocked(self, mock_sleep, mock_impl):
        mock_impl.side_effect = ScrapeError(
            ScrapeFailureReason.CONSENT_BLOCKED, "blocked", "LHR-NRT"
        )
        result = search_playwright_sync("LHR", "NRT", date(2026, 9, 1))
        assert result is None
        assert mock_impl.call_count == 1

    @patch("rtw.scraper.google_flights._search_playwright_impl")
    @patch("rtw.scraper.google_flights.time.sleep")
    def test_retry_backoff_delay(self, mock_sleep, mock_impl):
        mock_impl.side_effect = ScrapeError(
            ScrapeFailureReason.TIMEOUT, "timeout", "LHR-NRT"
        )
        search_playwright_sync("LHR", "NRT", date(2026, 9, 1))
        # Sleep called once between first and second attempt
        mock_sleep.assert_called_with(_RETRY_BACKOFF_S)

    @patch("rtw.scraper.google_flights._search_playwright_impl")
    @patch("rtw.scraper.google_flights.time.sleep")
    def test_no_retry_on_success(self, mock_sleep, mock_impl):
        expected = FlightPrice(
            origin="LHR", dest="NRT", carrier="JL",
            price_usd=2500.0, cabin="business",
        )
        mock_impl.return_value = expected
        result = search_playwright_sync("LHR", "NRT", date(2026, 9, 1))
        assert result == expected
        assert mock_impl.call_count == 1


class TestSearchPlaywrightSync:
    """Integration-style tests for the full playwright search flow."""

    def test_playwright_not_installed(self):
        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            result = search_playwright_sync("LHR", "NRT", date(2026, 9, 1))
            assert result is None

    @patch("rtw.scraper.google_flights._search_playwright_impl")
    @patch("rtw.scraper.google_flights.time.sleep")
    def test_backward_compat_no_max_stops(self, mock_sleep, mock_impl):
        """Call without max_stops kwarg works."""
        expected = FlightPrice(
            origin="LHR", dest="NRT", carrier="JL",
            price_usd=2500.0, cabin="business",
        )
        mock_impl.return_value = expected
        result = search_playwright_sync("LHR", "NRT", date(2026, 9, 1))
        assert result == expected


class TestConstants:
    """Test module-level constants exist with correct values."""

    def test_selectors_keys(self):
        for key in ("flight_card", "show_more", "airline", "price",
                     "stops", "stops_alt", "departure", "arrival", "duration"):
            assert key in _SELECTORS

    def test_consent_selectors_count(self):
        assert len(_CONSENT_SELECTORS) == 7

    def test_retry_constants(self):
        assert _MAX_ATTEMPTS == 2
        assert _RETRY_BACKOFF_S == 5.0


class TestCarrierHelpers:
    """Test carrier extraction and oneworld check."""

    def test_extract_carrier_iata_qatar(self):
        assert _extract_carrier_iata("Qatar Airways") == "QR"

    def test_extract_carrier_iata_jal(self):
        assert _extract_carrier_iata("Japan Airlines") == "JL"

    def test_extract_carrier_iata_unknown(self):
        assert _extract_carrier_iata("Unknown Carrier") == "UN"

    def test_is_oneworld_qatar(self):
        assert _is_oneworld("Qatar Airways") is True

    def test_is_oneworld_non_member(self):
        assert _is_oneworld("Lufthansa") is False

    def test_is_oneworld_ba(self):
        assert _is_oneworld("British Airways") is True


@pytest.mark.live
class TestLiveSmoke:
    """Live smoke tests — only run with `pytest -m live`."""

    def test_live_smoke_placeholder(self):
        """Placeholder — real live tests require Playwright install."""
        pytest.skip("Live tests disabled by default")
