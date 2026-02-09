"""Google Flights price scraping via Playwright (primary) and fast-flights (fallback).

All functions degrade gracefully to None when services are unavailable.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date as Date
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rate limiting: minimum seconds between scrape calls
_RATE_LIMIT_SECONDS = 2.0
_last_call_time: float = 0.0

# Retry / timeout constants
_MAX_ATTEMPTS = 2
_RETRY_BACKOFF_S = 5.0
_PAGE_LOAD_TIMEOUT_MS = 30000
_CARD_WAIT_TIMEOUT_MS = 10000
_CONSENT_VISIBILITY_TIMEOUT_MS = 500
_MAX_EXPAND_CLICKS = 5
_EXPAND_WAIT_MS = 2500
_EXPAND_PHASE_TIMEOUT_MS = 15000

# CSS selectors — centralised so changes happen in one place
_SELECTORS = {
    "flight_card": "li.pIav2d",
    "show_more": "button[aria-label*='more flights'], button[aria-label*='More flights']",
    "airline": ".sSHqwe",
    "price": ".YMlIz",
    "stops": ".EfT7Ae .ogfYpf",
    "stops_alt": ".VG3hNb",
    "departure": ".wtDjR .zxVSec",
    "arrival": ".XWcVob .zxVSec",
    "duration": ".gvkrdb",
}

# Consent-dismiss selectors — tried in order, first visible wins
_CONSENT_SELECTORS = [
    'button[aria-label="Accept all"]',
    "button:has-text('Accept all')",
    "button:has-text('Agree')",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Tout accepter')",
    "button#agree",
    "button#consent",
]

# User-agent for browser context
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Oneworld carrier data
# ---------------------------------------------------------------------------

_ONEWORLD_CARRIERS = {
    "american", "british airways", "cathay pacific", "finnair", "iberia",
    "japan airlines", "jal", "malaysia airlines", "qantas", "qatar airways",
    "royal air maroc", "royal jordanian", "srilankan", "alaska",
    "fiji airways", "oman air", "s7 airlines",
    # IATA codes as fallback
    "aa", "ba", "cx", "ay", "ib", "jl", "mh", "qf", "qr", "at", "rj",
    "ul", "as", "fj", "wy", "s7",
}

_CARRIER_IATA = {
    "american": "AA", "british airways": "BA", "cathay pacific": "CX",
    "finnair": "AY", "iberia": "IB", "japan airlines": "JL", "jal": "JL",
    "malaysia airlines": "MH", "qantas": "QF", "qatar airways": "QR",
    "royal air maroc": "AT", "royal jordanian": "RJ", "srilankan": "UL",
    "alaska": "AS", "fiji airways": "FJ", "oman air": "WY", "s7 airlines": "S7",
}

# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class ScrapeFailureReason(str, Enum):
    """Categorised reasons a scrape attempt can fail."""

    TIMEOUT = "timeout"
    CONSENT_BLOCKED = "consent_blocked"
    NO_RESULTS = "no_results"
    PARSE_ERROR = "parse_error"
    BROWSER_ERROR = "browser_error"


class ScrapeError(Exception):
    """Structured error from the Playwright scraper."""

    def __init__(self, reason: ScrapeFailureReason, message: str, route: str = ""):
        self.reason = reason
        self.route = route
        super().__init__(f"[{reason.value}] {route}: {message}")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class SearchBackend(str, Enum):
    """Which flight search backend to use."""

    AUTO = "auto"
    SERPAPI = "serpapi"
    FAST_FLIGHTS = "fast-flights"
    PLAYWRIGHT = "playwright"


@dataclass
class FlightPrice:
    """Price result from a flight search."""

    origin: str
    dest: str
    carrier: str
    price_usd: float
    cabin: str  # "economy", "business", "first"
    date: Optional[Date] = None
    source: str = "google_flights"  # "fast_flights", "playwright", or "serpapi"
    stops: Optional[int] = None
    # New fields (populated by SerpAPI, None for other backends)
    flight_number: Optional[str] = None
    duration_minutes: Optional[int] = None
    airline_name: Optional[str] = None

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _rate_limit() -> None:
    """Enforce minimum delay between scrape calls."""
    global _last_call_time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _last_call_time = time.time()


def _extract_carrier_iata(carrier_text: str) -> str:
    """Extract IATA code from carrier name text."""
    text = carrier_text.lower().strip()
    for name, code in _CARRIER_IATA.items():
        if name in text:
            return code
    return carrier_text[:2].upper() if len(carrier_text) >= 2 else "??"


def _is_oneworld(carrier_text: str) -> bool:
    """Check if any oneworld carrier appears in the text."""
    text = carrier_text.lower()
    return any(ow in text for ow in _ONEWORLD_CARRIERS)


def _parse_price(text: str) -> Optional[float]:
    """Extract USD price from text like '$5,026'."""
    m = re.search(r"\$([\d,]+)", text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None

# ---------------------------------------------------------------------------
# fast-flights search (unchanged)
# ---------------------------------------------------------------------------


def search_fast_flights(
    origin: str,
    dest: str,
    date: Date,
    cabin: str = "business",
) -> Optional[FlightPrice]:
    """Search Google Flights using the fast-flights library.

    Args:
        origin: 3-letter IATA airport code.
        dest: 3-letter IATA airport code.
        date: Flight date.
        cabin: Cabin class (economy, business, first).

    Returns:
        FlightPrice or None if search failed.
    """
    try:
        from fast_flights import FlightData, Passengers, get_flights
    except ImportError:
        logger.info("fast-flights library not available")
        return None

    _rate_limit()

    try:
        cabin_map = {
            "economy": "economy",
            "premium_economy": "premium-economy",
            "business": "business",
            "first": "first",
        }
        seat_label = cabin_map.get(cabin.lower(), "business")

        result = get_flights(
            flight_data=[
                FlightData(date=date.strftime("%Y-%m-%d"), from_airport=origin, to_airport=dest)
            ],
            trip="one-way",
            seat=seat_label,
            passengers=Passengers(adults=1),
        )

        if not result or not result.flights:
            logger.info("No fast-flights results for %s-%s on %s", origin, dest, date)
            return None

        best = min(result.flights, key=lambda f: f.price or float("inf"))
        if best.price is None:
            return None

        return FlightPrice(
            origin=origin.upper(),
            dest=dest.upper(),
            carrier=best.name or "Unknown",
            price_usd=float(best.price),
            cabin=cabin,
            date=date,
            source="fast_flights",
        )

    except Exception as exc:
        msg = str(exc).split("\n")[0][:100]
        logger.debug("fast-flights failed for %s-%s: %s", origin, dest, msg)
        return None

# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------


def _dismiss_consent(page) -> bool:
    """Try to dismiss cookie/consent dialogs.

    Iterates through ``_CONSENT_SELECTORS`` and clicks the first visible button.
    Returns True if a consent button was found and clicked, False otherwise.
    """
    for selector in _CONSENT_SELECTORS:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=_CONSENT_VISIBILITY_TIMEOUT_MS):
                btn.click()
                page.wait_for_load_state("networkidle", timeout=8000)
                logger.debug("Dismissed consent via: %s", selector)
                return True
        except Exception:
            continue
    logger.debug("No consent dialog found (or already dismissed)")
    return False


def _expand_all_results(page) -> int:
    """Click 'show more flights' until all results are visible.

    Returns the total number of flight cards after expansion.
    """
    start = time.monotonic()
    clicks = 0
    selector = _SELECTORS["show_more"]

    while clicks < _MAX_EXPAND_CLICKS:
        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms > _EXPAND_PHASE_TIMEOUT_MS:
            logger.debug("Expansion phase timed out after %.1fs", elapsed_ms / 1000)
            break
        try:
            btn = page.locator(selector).first
            btn.wait_for(state="visible", timeout=3000)
            btn.click()
            clicks += 1
            page.wait_for_timeout(_EXPAND_WAIT_MS)
        except Exception:
            break  # No more buttons visible

    count = len(page.locator(_SELECTORS["flight_card"]).all())
    logger.debug("Found %d flight cards after %d expansion clicks", count, clicks)
    return count


def _parse_stops(card_element) -> Optional[int]:
    """Extract the number of stops from a flight card.

    Returns 0 for nonstop, N for N stops, or None if unparseable.
    """
    # Strategy 1: use dedicated selector
    try:
        stops_el = card_element.locator(_SELECTORS["stops"]).first
        stops_text = stops_el.inner_text(timeout=1000)
    except Exception:
        # Strategy 2: regex on full card text
        try:
            stops_text = card_element.inner_text()
        except Exception:
            return None

    if not stops_text:
        return None

    text_lower = stops_text.lower()
    if "nonstop" in text_lower:
        return 0

    m = re.search(r"(\d+)\s*stops?", text_lower)
    if m:
        return int(m.group(1))

    return None


def _parse_flight_card(card, origin: str, dest: str, date: Date, cabin: str) -> Optional[dict]:
    """Parse a single flight result card into a dict.

    Returns dict with keys: price, carrier_text, carrier_code, stops.
    Returns None if the card cannot be parsed (missing price, too few lines, etc).
    """
    try:
        text = card.inner_text()
    except Exception:
        return None

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 4:
        return None

    price = _parse_price(text)
    if price is None:
        return None

    # Lines layout: time, -, time, carrier(s), duration, route, stops, price
    carrier_text = lines[3] if len(lines) > 3 else ""
    carrier_code = _extract_carrier_iata(carrier_text)
    stops = _parse_stops(card)

    return {
        "price": price,
        "carrier_text": carrier_text,
        "carrier_code": carrier_code,
        "stops": stops,
    }

# ---------------------------------------------------------------------------
# Playwright search (refactored)
# ---------------------------------------------------------------------------


def _search_playwright_impl(
    origin: str,
    dest: str,
    date: Date,
    cabin: str = "business",
    oneworld_only: bool = True,
    max_stops: Optional[int] = None,
) -> Optional[FlightPrice]:
    """Single-attempt Playwright search against Google Flights.

    Raises ScrapeError on failure so the retry wrapper can decide whether to retry.
    """
    from playwright.sync_api import sync_playwright

    route = f"{origin}-{dest}"

    cabin_query = {"business": "business+class", "first": "first+class"}.get(
        cabin.lower(), ""
    )
    url = (
        f"https://www.google.com/travel/flights?"
        f"q=flights+from+{origin}+to+{dest}+on+{date.isoformat()}"
        f"+{cabin_query}&curr=USD"
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=_USER_AGENT,
            )
            page = context.new_page()
            try:
                page.goto(url, timeout=_PAGE_LOAD_TIMEOUT_MS)

                _dismiss_consent(page)

                # Wait for flight cards instead of flat timeout
                try:
                    page.wait_for_selector(
                        _SELECTORS["flight_card"], timeout=_CARD_WAIT_TIMEOUT_MS
                    )
                except Exception:
                    raise ScrapeError(
                        ScrapeFailureReason.NO_RESULTS,
                        f"No flight cards appeared within {_CARD_WAIT_TIMEOUT_MS}ms",
                        route=route,
                    )

                # Expand hidden results before parsing
                _expand_all_results(page)

                results = page.locator(_SELECTORS["flight_card"]).all()
                if not results:
                    raise ScrapeError(
                        ScrapeFailureReason.NO_RESULTS,
                        "Flight card selector matched 0 elements",
                        route=route,
                    )

                best: Optional[FlightPrice] = None

                for card in results:
                    parsed = _parse_flight_card(card, origin, dest, date, cabin)
                    if parsed is None:
                        continue

                    # Carrier filter
                    if oneworld_only and not _is_oneworld(parsed["carrier_text"]):
                        continue

                    # Stops filter
                    if max_stops is not None and parsed["stops"] is not None and parsed["stops"] > max_stops:
                        continue

                    fp = FlightPrice(
                        origin=origin.upper(),
                        dest=dest.upper(),
                        carrier=parsed["carrier_code"],
                        price_usd=parsed["price"],
                        cabin=cabin,
                        date=date,
                        source="playwright",
                        stops=parsed["stops"],
                    )

                    if best is None or fp.price_usd < best.price_usd:
                        best = fp

                if best:
                    logger.info(
                        "Playwright found %s-%s: %s $%.0f",
                        origin, dest, best.carrier, best.price_usd,
                    )
                else:
                    logger.info(
                        "No %sflights for %s-%s on %s",
                        "oneworld " if oneworld_only else "", origin, dest, date,
                    )

                return best

            finally:
                page.close()
                context.close()
                browser.close()

    except ScrapeError:
        raise  # Let the retry wrapper handle it
    except Exception as exc:
        raise ScrapeError(
            ScrapeFailureReason.BROWSER_ERROR,
            str(exc)[:200],
            route=route,
        ) from exc


def search_playwright_sync(
    origin: str,
    dest: str,
    date: Date,
    cabin: str = "business",
    oneworld_only: bool = True,
    max_stops: Optional[int] = None,
) -> Optional[FlightPrice]:
    """Scrape Google Flights via Playwright (sync) with retry.

    Returns the cheapest flight found, optionally filtered to oneworld carriers.
    Returns None if Playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        logger.info("Playwright not installed")
        return None

    _rate_limit()

    route = f"{origin}-{dest}"
    last_error: Optional[ScrapeError] = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return _search_playwright_impl(origin, dest, date, cabin, oneworld_only, max_stops)
        except ScrapeError as e:
            if e.reason == ScrapeFailureReason.CONSENT_BLOCKED:
                logger.warning("Consent blocked for %s, not retrying: %s", route, e)
                return None
            last_error = e
            if attempt < _MAX_ATTEMPTS:
                logger.warning(
                    "Attempt %d/%d failed for %s: %s. Retrying in %.0fs",
                    attempt, _MAX_ATTEMPTS, route, e, _RETRY_BACKOFF_S,
                )
                time.sleep(_RETRY_BACKOFF_S)

    # Exhausted retries — log and return None for backward compatibility
    logger.warning("Playwright search failed for %s after %d attempts: %s",
                    route, _MAX_ATTEMPTS, last_error)
    return None
