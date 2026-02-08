"""Tests for ExpertFlyer scraper module."""

from datetime import date
from unittest.mock import patch

import pytest

from rtw.scraper.expertflyer import ExpertFlyerScraper


class TestExpertFlyerScraper:
    """Test ExpertFlyerScraper graceful degradation."""

    def test_credentials_unavailable_when_keyring_missing(self):
        """credentials_available() returns False when keyring is not importable."""
        scraper = ExpertFlyerScraper()
        with patch.dict("sys.modules", {"keyring": None}):
            # Force re-check by clearing cached credentials
            scraper._username = None
            scraper._password = None
            assert scraper.credentials_available() is False

    def test_credentials_unavailable_when_not_configured(self):
        """credentials_available() returns False when credentials not in keyring."""
        scraper = ExpertFlyerScraper()
        with patch("rtw.scraper.expertflyer.keyring", create=True) as mock_keyring:
            mock_keyring.get_password.return_value = None
            scraper._username = None
            scraper._password = None

            # Patch the import inside the method
            import types

            mock_kr = types.ModuleType("keyring")
            mock_kr.get_password = lambda service, key: None

            with patch.dict("sys.modules", {"keyring": mock_kr}):
                scraper._username = None
                scraper._password = None
                assert scraper.credentials_available() is False

    @pytest.mark.asyncio
    async def test_check_availability_no_credentials(self):
        """check_availability returns None when no credentials available."""
        scraper = ExpertFlyerScraper()

        # Ensure no credentials
        import types

        mock_kr = types.ModuleType("keyring")
        mock_kr.get_password = lambda service, key: None

        with patch.dict("sys.modules", {"keyring": mock_kr}):
            scraper._username = None
            scraper._password = None
            result = await scraper.check_availability(
                origin="LHR",
                dest="NRT",
                date=date(2025, 6, 15),
                carrier="JL",
                booking_class="D",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_check_availability_no_playwright(self):
        """check_availability returns None when Playwright not available."""
        scraper = ExpertFlyerScraper()
        # Set fake credentials
        scraper._username = "testuser"
        scraper._password = "testpass"

        with patch("rtw.scraper.BrowserManager") as mock_bm:
            mock_bm.available.return_value = False
            result = await scraper.check_availability(
                origin="LHR",
                dest="NRT",
                date=date(2025, 6, 15),
                carrier="JL",
            )
            assert result is None

    def test_scraper_init(self):
        """ExpertFlyerScraper initializes with no credentials."""
        scraper = ExpertFlyerScraper()
        assert scraper._username is None
        assert scraper._password is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_availability_check(self):
        """Integration test: check real ExpertFlyer availability."""
        scraper = ExpertFlyerScraper()
        if not scraper.credentials_available():
            pytest.skip("ExpertFlyer credentials not configured")

        result = await scraper.check_availability(
            origin="LHR",
            dest="NRT",
            date=date(2025, 9, 1),
            carrier="JL",
        )
        # Result may be None (stub) but should not raise
        assert result is None or isinstance(result, dict)
