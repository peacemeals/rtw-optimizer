"""Tests for SerpAPI Google Flights integration."""

from datetime import date
from unittest.mock import patch, MagicMock

import pytest
import requests

from rtw.scraper.serpapi_flights import (
    SerpAPIAuthError,
    SerpAPIError,
    SerpAPIQuotaError,
    _extract_carrier_iata_from_serpapi,
    _parse_serpapi_response,
    search_serpapi,
    serpapi_available,
    _CABIN_MAP,
    _STOPS_MAP,
)
from rtw.scraper.google_flights import FlightPrice

# ---------------------------------------------------------------------------
# Response fixtures
# ---------------------------------------------------------------------------

RESPONSE_BASIC = {
    "best_flights": [
        {
            "flights": [{"airline": "Qatar Airways", "flight_number": "QR 807"}],
            "price": 3200,
            "total_duration": 810,
            "layovers": [],
        }
    ],
    "other_flights": [
        {
            "flights": [{"airline": "Cathay Pacific", "flight_number": "CX 101"}],
            "price": 2450,
            "total_duration": 540,
            "layovers": [],
        }
    ],
}

RESPONSE_BEST_ONLY = {
    "best_flights": [
        {
            "flights": [{"airline": "British Airways", "flight_number": "BA 15"}],
            "price": 1800,
            "total_duration": 420,
            "layovers": [],
        }
    ],
    "other_flights": [],
}

RESPONSE_EMPTY = {"best_flights": [], "other_flights": []}

RESPONSE_NO_ARRAYS = {"search_metadata": {"status": "success"}}

RESPONSE_API_ERROR = {"error": "Invalid API key"}

RESPONSE_NO_PRICES = {
    "best_flights": [
        {"flights": [{"airline": "Qatar Airways", "flight_number": "QR 807"}], "layovers": []}
    ],
    "other_flights": [],
}

RESPONSE_UNKNOWN_AIRLINE = {
    "best_flights": [
        {
            "flights": [{"airline": "Zippy Air", "flight_number": "ZA 100"}],
            "price": 999,
            "total_duration": 300,
            "layovers": [],
        }
    ],
    "other_flights": [],
}

RESPONSE_TWO_STOPS = {
    "best_flights": [
        {
            "flights": [
                {"airline": "American Airlines", "flight_number": "AA 100"},
                {"airline": "American Airlines", "flight_number": "AA 200"},
                {"airline": "American Airlines", "flight_number": "AA 300"},
            ],
            "price": 1500,
            "total_duration": 1200,
            "layovers": [
                {"name": "Dallas/Fort Worth", "duration": 120},
                {"name": "Miami", "duration": 90},
            ],
        }
    ],
    "other_flights": [],
}

TEST_DATE = date(2025, 9, 15)


# ---------------------------------------------------------------------------
# TestSerpAPIAvailable
# ---------------------------------------------------------------------------


class TestSerpAPIAvailable:
    def test_available_when_key_set(self, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key_123")
        assert serpapi_available() is True

    def test_not_available_when_key_unset(self, monkeypatch):
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
        assert serpapi_available() is False

    def test_not_available_when_key_empty(self, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "   ")
        assert serpapi_available() is False


# ---------------------------------------------------------------------------
# TestSearchSerpAPI
# ---------------------------------------------------------------------------


def _mock_response(status_code=200, json_data=None, raise_timeout=False, bad_json=False):
    """Create a mock requests.Response."""
    if raise_timeout:
        raise requests.Timeout("Connection timed out")
    resp = MagicMock()
    resp.status_code = status_code
    if bad_json:
        resp.json.side_effect = ValueError("No JSON")
    else:
        resp.json.return_value = json_data or {}
    return resp


class TestSearchSerpAPI:
    def test_returns_none_without_key(self, monkeypatch):
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
        result = search_serpapi("SYD", "HKG", TEST_DATE)
        assert result is None

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_successful_search_picks_cheapest(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        mock_get.return_value = _mock_response(json_data=RESPONSE_BASIC)
        result = search_serpapi("SYD", "HKG", TEST_DATE)
        assert result is not None
        assert result.price_usd == 2450  # other_flights cheaper than best_flights

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_successful_search_fields(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        mock_get.return_value = _mock_response(json_data=RESPONSE_BASIC)
        result = search_serpapi("SYD", "HKG", TEST_DATE, cabin="business")
        assert result.origin == "SYD"
        assert result.dest == "HKG"
        assert result.carrier == "CX"
        assert result.cabin == "business"
        assert result.date == TEST_DATE
        assert result.source == "serpapi"
        assert result.stops == 0
        assert result.flight_number == "CX 101"
        assert result.duration_minutes == 540
        assert result.airline_name == "Cathay Pacific"

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_request_params_correct(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "my_key")
        mock_get.return_value = _mock_response(json_data=RESPONSE_EMPTY)
        search_serpapi("SYD", "LHR", TEST_DATE, cabin="business", oneworld_only=True)
        args, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        assert params["engine"] == "google_flights"
        assert params["departure_id"] == "SYD"
        assert params["arrival_id"] == "LHR"
        assert params["outbound_date"] == "2025-09-15"
        assert params["type"] == 2
        assert params["travel_class"] == 3
        assert params["currency"] == "USD"
        assert params["deep_search"] == "true"
        assert params["include_airlines"] == "ONEWORLD"
        assert params["api_key"] == "my_key"

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_request_params_no_oneworld(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        mock_get.return_value = _mock_response(json_data=RESPONSE_EMPTY)
        search_serpapi("SYD", "LHR", TEST_DATE, oneworld_only=False)
        params = mock_get.call_args[1]["params"]
        assert "include_airlines" not in params

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_request_params_nonstop(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        mock_get.return_value = _mock_response(json_data=RESPONSE_EMPTY)
        search_serpapi("SYD", "LHR", TEST_DATE, max_stops=0)
        params = mock_get.call_args[1]["params"]
        assert params["stops"] == 1  # 0 -> 1 in SerpAPI mapping

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_auth_error_raises_on_401(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "bad_key")
        mock_get.return_value = _mock_response(status_code=401)
        with pytest.raises(SerpAPIAuthError):
            search_serpapi("SYD", "LHR", TEST_DATE)

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_quota_error_raises_on_429(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        mock_get.return_value = _mock_response(status_code=429)
        with pytest.raises(SerpAPIQuotaError):
            search_serpapi("SYD", "LHR", TEST_DATE)

    @patch("rtw.scraper.serpapi_flights.requests.get", side_effect=requests.Timeout("timeout"))
    def test_timeout_returns_none(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        result = search_serpapi("SYD", "LHR", TEST_DATE)
        assert result is None

    @patch("rtw.scraper.serpapi_flights.requests.get", side_effect=requests.ConnectionError("fail"))
    def test_network_error_returns_none(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        result = search_serpapi("SYD", "LHR", TEST_DATE)
        assert result is None

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_http_500_returns_none(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        mock_get.return_value = _mock_response(status_code=500)
        result = search_serpapi("SYD", "LHR", TEST_DATE)
        assert result is None

    @patch("rtw.scraper.serpapi_flights.requests.get")
    def test_malformed_json_returns_none(self, mock_get, monkeypatch):
        monkeypatch.setenv("SERPAPI_API_KEY", "test_key")
        mock_get.return_value = _mock_response(bad_json=True)
        result = search_serpapi("SYD", "LHR", TEST_DATE)
        assert result is None


# ---------------------------------------------------------------------------
# TestParseSerpAPIResponse
# ---------------------------------------------------------------------------


class TestParseSerpAPIResponse:
    def test_picks_cheapest_across_both_arrays(self):
        result = _parse_serpapi_response(RESPONSE_BASIC, "SYD", "HKG", TEST_DATE, "business")
        assert result.price_usd == 2450

    def test_best_only_response(self):
        result = _parse_serpapi_response(RESPONSE_BEST_ONLY, "SYD", "LHR", TEST_DATE, "business")
        assert result.price_usd == 1800
        assert result.carrier == "BA"

    def test_empty_both_arrays(self):
        result = _parse_serpapi_response(RESPONSE_EMPTY, "SYD", "LHR", TEST_DATE, "business")
        assert result is None

    def test_missing_arrays_returns_none(self):
        result = _parse_serpapi_response(RESPONSE_NO_ARRAYS, "SYD", "LHR", TEST_DATE, "business")
        assert result is None

    def test_api_error_in_body(self):
        result = _parse_serpapi_response(RESPONSE_API_ERROR, "SYD", "LHR", TEST_DATE, "business")
        assert result is None

    def test_no_prices_returns_none(self):
        result = _parse_serpapi_response(RESPONSE_NO_PRICES, "SYD", "LHR", TEST_DATE, "business")
        assert result is None

    def test_extracts_flight_number(self):
        result = _parse_serpapi_response(RESPONSE_BASIC, "SYD", "HKG", TEST_DATE, "business")
        assert result.flight_number == "CX 101"

    def test_extracts_duration(self):
        result = _parse_serpapi_response(RESPONSE_BASIC, "SYD", "HKG", TEST_DATE, "business")
        assert result.duration_minutes == 540

    def test_extracts_stops_count(self):
        result = _parse_serpapi_response(RESPONSE_BASIC, "SYD", "HKG", TEST_DATE, "business")
        assert result.stops == 0

    def test_two_stop_itinerary(self):
        result = _parse_serpapi_response(RESPONSE_TWO_STOPS, "JFK", "MIA", TEST_DATE, "business")
        assert result.stops == 2
        assert result.duration_minutes == 1200


# ---------------------------------------------------------------------------
# TestExtractCarrierIATA
# ---------------------------------------------------------------------------


class TestExtractCarrierIATA:
    def test_qatar_airways(self):
        assert _extract_carrier_iata_from_serpapi("Qatar Airways") == "QR"

    def test_british_airways(self):
        assert _extract_carrier_iata_from_serpapi("British Airways") == "BA"

    def test_cathay_pacific(self):
        assert _extract_carrier_iata_from_serpapi("Cathay Pacific") == "CX"

    def test_japan_airlines(self):
        assert _extract_carrier_iata_from_serpapi("Japan Airlines") == "JL"

    def test_unknown_airline_fallback(self):
        assert _extract_carrier_iata_from_serpapi("Zippy Air") == "ZI"

    def test_case_insensitive(self):
        assert _extract_carrier_iata_from_serpapi("QATAR AIRWAYS") == "QR"


# ---------------------------------------------------------------------------
# TestSerpAPIExceptions
# ---------------------------------------------------------------------------


class TestSerpAPIExceptions:
    def test_auth_error_is_serpapi_error(self):
        assert issubclass(SerpAPIAuthError, SerpAPIError)

    def test_quota_error_is_serpapi_error(self):
        assert issubclass(SerpAPIQuotaError, SerpAPIError)

    def test_serpapi_error_is_exception(self):
        assert issubclass(SerpAPIError, Exception)

    def test_auth_error_message(self):
        exc = SerpAPIAuthError("bad key")
        assert str(exc) == "bad key"

    def test_quota_error_message(self):
        exc = SerpAPIQuotaError("exceeded")
        assert str(exc) == "exceeded"


# ---------------------------------------------------------------------------
# TestCabinClassMapping
# ---------------------------------------------------------------------------


class TestCabinClassMapping:
    def test_economy_maps_to_1(self):
        assert _CABIN_MAP["economy"] == 1

    def test_business_maps_to_3(self):
        assert _CABIN_MAP["business"] == 3

    def test_first_maps_to_4(self):
        assert _CABIN_MAP["first"] == 4

    def test_unknown_cabin_defaults_to_3(self):
        assert _CABIN_MAP.get("ultra_first", 3) == 3


# ---------------------------------------------------------------------------
# TestLiveIntegration (gated)
# ---------------------------------------------------------------------------


class TestLiveIntegration:
    @pytest.mark.integration
    @pytest.mark.slow
    def test_live_search_known_route(self):
        if not serpapi_available():
            pytest.skip("SERPAPI_API_KEY not set")
        result = search_serpapi("SYD", "HKG", date(2025, 12, 1), cabin="business")
        # May return None if no flights, but should not crash
        if result is not None:
            assert result.source == "serpapi"
            assert result.price_usd > 0
