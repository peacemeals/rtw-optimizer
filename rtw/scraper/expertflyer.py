"""ExpertFlyer availability scraper.

Checks award/premium class availability on ExpertFlyer using Playwright.
Credentials are retrieved from macOS Keychain via the keyring library.

All functions degrade gracefully when credentials or services are unavailable.
"""

from __future__ import annotations

import logging
from datetime import date as Date
from typing import Optional

logger = logging.getLogger(__name__)

_EXPERTFLYER_SERVICE = "expertflyer.com"


class ExpertFlyerScraper:
    """Scrape ExpertFlyer for seat availability.

    Requires ExpertFlyer credentials stored in macOS Keychain:
        keyring set expertflyer.com <username>
    """

    def __init__(self) -> None:
        self._username: Optional[str] = None
        self._password: Optional[str] = None

    def _get_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """Retrieve ExpertFlyer credentials from system keyring.

        Returns:
            Tuple of (username, password), either may be None.
        """
        if self._username is not None:
            return self._username, self._password

        try:
            import keyring
        except ImportError:
            logger.info("keyring library not available - cannot retrieve ExpertFlyer credentials")
            return None, None

        try:
            # Convention: username stored as the 'account' in keyring
            # with service "expertflyer.com"
            username = keyring.get_password(_EXPERTFLYER_SERVICE, "username")
            password = keyring.get_password(_EXPERTFLYER_SERVICE, "password")

            if not username or not password:
                logger.info("ExpertFlyer credentials not found in keyring")
                return None, None

            self._username = username
            self._password = password
            return username, password

        except Exception as exc:
            logger.warning("Failed to retrieve ExpertFlyer credentials: %s", exc)
            return None, None

    def credentials_available(self) -> bool:
        """Check whether ExpertFlyer credentials are configured."""
        username, password = self._get_credentials()
        return username is not None and password is not None

    async def check_availability(
        self,
        origin: str,
        dest: str,
        date: Date,
        carrier: str,
        booking_class: str = "D",
    ) -> Optional[dict]:
        """Check seat availability for a specific route and class.

        Args:
            origin: 3-letter IATA airport code.
            dest: 3-letter IATA airport code.
            date: Flight date.
            carrier: 2-letter airline code.
            booking_class: Booking class to check (default "D" for business award).

        Returns:
            Dict with availability info, or None if unavailable/failed.
            Example: {"origin": "LHR", "dest": "NRT", "carrier": "JL",
                      "class": "D", "available": True, "seats": 2}
        """
        username, password = self._get_credentials()
        if not username or not password:
            logger.info("Skipping ExpertFlyer check - no credentials")
            return None

        try:
            from rtw.scraper import BrowserManager

            if not BrowserManager.available():
                logger.info("Playwright not available for ExpertFlyer scraping")
                return None

            async with BrowserManager() as browser:
                return await self._scrape_availability(
                    browser, origin, dest, date, carrier, booking_class, username, password
                )

        except Exception as exc:
            logger.warning(
                "ExpertFlyer check failed for %s %s-%s: %s",
                carrier,
                origin,
                dest,
                exc,
            )
            return None

    async def _scrape_availability(
        self,
        browser,
        origin: str,
        dest: str,
        date: Date,
        carrier: str,
        booking_class: str,
        username: str,
        password: str,
    ) -> Optional[dict]:
        """Internal: Perform the actual ExpertFlyer scrape.

        NOTE: This is a P2 stub. Full implementation would:
        1. Navigate to ExpertFlyer login page
        2. Authenticate with username/password
        3. Search for the route/date/carrier
        4. Parse the availability grid for the booking class
        5. Return structured availability data

        Returns:
            Dict with availability info, or None.
        """
        logger.info(
            "ExpertFlyer stub: would check %s %s-%s class %s on %s",
            carrier,
            origin,
            dest,
            booking_class,
            date,
        )
        # Stub: actual implementation would scrape the ExpertFlyer site
        return None
