"""Tests for ExpertFlyer HTML parser using real fixture data."""

from pathlib import Path

import pytest

from rtw.scraper.expertflyer import parse_availability_html

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


class TestParseAvailabilityHtml:
    @pytest.fixture
    def lhr_hkg_html(self):
        """Real ExpertFlyer results page: LHR→HKG, D-class filtered."""
        path = FIXTURE_DIR / "ef_results_lhr_hkg_d.html"
        if not path.exists():
            pytest.skip("HTML fixture not found")
        return path.read_text(encoding="utf-8")

    def test_parses_flights(self, lhr_hkg_html):
        results = parse_availability_html(lhr_hkg_html, "D")
        assert len(results) > 0
        # We know from the capture there are 11 flight rows
        assert len(results) >= 7

    def test_d_class_values(self, lhr_hkg_html):
        results = parse_availability_html(lhr_hkg_html, "D")
        seats = [r["seats"] for r in results if r["seats"] is not None]
        assert len(seats) > 0
        # All values should be 0-9
        for s in seats:
            assert 0 <= s <= 9
        # We know D9, D5, D3 are in the results
        assert 9 in seats
        assert 5 in seats

    def test_carrier_extraction(self, lhr_hkg_html):
        results = parse_availability_html(lhr_hkg_html, "D")
        carriers = {r["carrier"] for r in results if r["carrier"]}
        # CX and BA should be present
        assert "CX" in carriers

    def test_airport_extraction(self, lhr_hkg_html):
        results = parse_availability_html(lhr_hkg_html, "D")
        # First result should have LHR origin
        origins = [r["origin"] for r in results if r["origin"]]
        assert "LHR" in origins

    def test_empty_html(self):
        results = parse_availability_html("<html><body></body></html>", "D")
        assert results == []

    def test_no_matching_class(self, lhr_hkg_html):
        # Search for Z class (should find nothing)
        results = parse_availability_html(lhr_hkg_html, "Z")
        seats = [r["seats"] for r in results if r["seats"] is not None]
        assert len(seats) == 0

    # --- T012: Detailed accuracy tests ---

    def test_exact_flight_count(self, lhr_hkg_html):
        """Fixture has exactly 11 flight rows."""
        results = parse_availability_html(lhr_hkg_html, "D")
        assert len(results) == 11

    def test_carrier_set(self, lhr_hkg_html):
        """Known carriers in the LHR→HKG results."""
        results = parse_availability_html(lhr_hkg_html, "D")
        carriers = {r["carrier"] for r in results if r["carrier"]}
        assert "CX" in carriers
        assert "BA" in carriers

    def test_specific_flight_numbers(self, lhr_hkg_html):
        """Verify known CX flight numbers are extracted."""
        results = parse_availability_html(lhr_hkg_html, "D")
        flight_numbers = {r["flight_number"] for r in results if r["flight_number"]}
        assert "CX252" in flight_numbers
        assert "CX238" in flight_numbers
        assert "BA31" in flight_numbers

    def test_origin_airports(self, lhr_hkg_html):
        """LHR should be the primary origin."""
        results = parse_availability_html(lhr_hkg_html, "D")
        origins = [r["origin"] for r in results if r["origin"]]
        assert origins[0] == "LHR"  # First flight departs LHR
        # Most flights originate from LHR
        lhr_count = sum(1 for o in origins if o == "LHR")
        assert lhr_count >= 4

    def test_destination_airports(self, lhr_hkg_html):
        """HKG should be the primary destination."""
        results = parse_availability_html(lhr_hkg_html, "D")
        dests = [r["destination"] for r in results if r["destination"]]
        hkg_count = sum(1 for d in dests if d == "HKG")
        assert hkg_count >= 4

    def test_seat_distribution(self, lhr_hkg_html):
        """Known seat values: D9, D5, D3."""
        results = parse_availability_html(lhr_hkg_html, "D")
        seats = [r["seats"] for r in results if r["seats"] is not None]
        unique_seats = set(seats)
        assert 9 in unique_seats  # CX flights: D9
        assert 5 in unique_seats  # BA 31: D5
        assert 3 in unique_seats  # Codeshare flights: D3

    def test_first_row_is_cx252(self, lhr_hkg_html):
        """First parsed flight should be CX 252 LHR→HKG D9."""
        results = parse_availability_html(lhr_hkg_html, "D")
        first = results[0]
        assert first["carrier"] == "CX"
        assert first["flight_number"] == "CX252"
        assert first["origin"] == "LHR"
        assert first["destination"] == "HKG"
        assert first["seats"] == 9

    def test_all_results_have_booking_class(self, lhr_hkg_html):
        """Every result should have booking_class='D'."""
        results = parse_availability_html(lhr_hkg_html, "D")
        for r in results:
            assert r["booking_class"] == "D"
