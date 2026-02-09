"""Shared fixtures for scraper tests."""

import pytest


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """Disable rate limiting in SerpAPI tests to avoid 2s delays."""
    try:
        monkeypatch.setattr("rtw.scraper.serpapi_flights._rate_limit", lambda: None)
    except AttributeError:
        pass  # Module not imported yet, that's fine
