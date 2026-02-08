"""Scraper module for RTW Optimizer.

Provides browser automation, flight price scraping, and availability checking.
All scrapers degrade gracefully when external services are unavailable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class BrowserManager:
    """Async context manager for Playwright browser lifecycle.

    Usage::

        async with BrowserManager() as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")

    If Playwright is not installed, entering the context manager raises
    a clear error. Use ``BrowserManager.available()`` to check first.
    """

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._playwright = None
        self._browser = None

    @staticmethod
    def available() -> bool:
        """Check whether Playwright is importable."""
        try:
            import playwright  # noqa: F401

            return True
        except ImportError:
            return False

    async def __aenter__(self):
        """Launch Chromium and return the browser instance."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
        except Exception as exc:
            logger.warning("Failed to launch browser: %s", exc)
            await self._playwright.stop()
            self._playwright = None
            raise
        return self._browser

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close browser and stop Playwright."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.warning("Error closing browser: %s", exc)
            self._browser = None

        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("Error stopping Playwright: %s", exc)
            self._playwright = None

        return None  # Don't suppress exceptions


# Re-export key classes for convenient imports
from rtw.scraper.cache import ScrapeCache  # noqa: E402, F401

__all__ = ["BrowserManager", "ScrapeCache"]
