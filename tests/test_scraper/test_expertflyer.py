"""Tests for ExpertFlyer scraper module."""

import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from rtw.scraper.expertflyer import (
    ExpertFlyerScraper,
    ScrapeError,
    SessionExpiredError,
    parse_availability_html,
)


class TestExpertFlyerScraper:
    """Test ExpertFlyerScraper session-based approach."""

    def test_scraper_init_no_session(self):
        scraper = ExpertFlyerScraper()
        assert scraper._session_path is None
        assert scraper._query_count == 0

    def test_scraper_init_with_session(self, tmp_path):
        path = str(tmp_path / "session.json")
        scraper = ExpertFlyerScraper(session_path=path)
        assert scraper._session_path == path

    @patch("rtw.scraper.expertflyer._get_credentials", return_value=None)
    def test_check_availability_no_credentials(self, mock_creds):
        """Returns None when no credentials configured."""
        scraper = ExpertFlyerScraper()
        result = scraper.check_availability(
            origin="LHR",
            dest="HKG",
            date=datetime.date(2026, 3, 10),
            carrier="CX",
        )
        assert result is None

    def test_build_results_url(self):
        scraper = ExpertFlyerScraper()
        url = scraper._build_results_url(
            origin="LHR",
            dest="HKG",
            date=datetime.date(2026, 3, 10),
            booking_class="D",
            carrier="CX",
        )
        assert "origin=LHR" in url
        assert "destination=HKG" in url
        assert "classFilter=D" in url
        assert "airLineCodes=CX" in url
        assert "resultsDisplay=single" in url
        assert "/air/availability/results" in url

    def test_build_results_url_no_carrier(self):
        scraper = ExpertFlyerScraper()
        url = scraper._build_results_url(
            origin="SYD",
            dest="LAX",
            date=datetime.date(2026, 5, 1),
        )
        assert "airLineCodes=" in url
        assert "origin=SYD" in url

    def test_session_expired_error(self):
        err = SessionExpiredError()
        assert err.error_type == "SESSION_EXPIRED"
        assert isinstance(err, ScrapeError)

    def test_scrape_error(self):
        err = ScrapeError("timeout", error_type="TIMEOUT")
        assert err.error_type == "TIMEOUT"
        assert "timeout" in str(err)


class TestParseAvailabilityHtml:
    """Test the standalone HTML parser."""

    @pytest.fixture
    def fixture_html(self):
        path = Path(__file__).parent.parent / "fixtures" / "ef_results_lhr_hkg_d.html"
        if not path.exists():
            pytest.skip("ExpertFlyer fixture not found")
        return path.read_text(encoding="utf-8")

    def test_parse_real_fixture(self, fixture_html):
        results = parse_availability_html(fixture_html, "D")
        assert len(results) >= 7
        # All results should have carrier
        carriers = [r["carrier"] for r in results if r["carrier"]]
        assert "CX" in carriers

    def test_d_class_seats(self, fixture_html):
        results = parse_availability_html(fixture_html, "D")
        seats = [r["seats"] for r in results if r["seats"] is not None]
        assert 9 in seats  # CX flights had D9
        assert 5 in seats  # BA 31 had D5

    def test_empty_html(self):
        results = parse_availability_html("<html></html>", "D")
        assert results == []

    @pytest.mark.integration
    def test_real_availability_check(self):
        """Integration test: requires valid ExpertFlyer session."""
        session_path = Path.home() / ".rtw" / "expertflyer_session.json"
        if not session_path.exists():
            pytest.skip("ExpertFlyer session not configured")

        scraper = ExpertFlyerScraper(session_path=str(session_path))
        result = scraper.check_availability(
            origin="LHR",
            dest="HKG",
            date=datetime.date(2026, 3, 15),
            carrier="CX",
        )
        assert result is not None
        assert result.origin == "LHR"
        assert result.destination == "HKG"
