"""ExpertFlyer D-class availability scraper.

Checks booking class availability on ExpertFlyer using Playwright with
programmatic Auth0 login via credentials from macOS Keychain.

Constructs results URLs directly (no form filling) and parses the
HTML table.

Key discovery: ExpertFlyer results URL is directly constructable:
    /air/availability/results?origin=LHR&destination=HKG&...&classFilter=D

Table structure: single <table> with <tbody> per flight group,
each containing a connection header row and flight data rows.
D-class shown as "D9", "D5", "D0" etc in the Available Classes column.
"""

from __future__ import annotations

import datetime
import logging
import random
import re
import time
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from rtw.verify.models import DClassResult

logger = logging.getLogger(__name__)

_EXPERTFLYER_BASE = "https://www.expertflyer.com"
_RESULTS_URL = f"{_EXPERTFLYER_BASE}/air/availability/results"
_LOGIN_URL = f"{_EXPERTFLYER_BASE}/auth/login"

# Rate limiting
_MIN_QUERY_INTERVAL = 5  # seconds between queries
_DAILY_SOFT_LIMIT = 50  # warn after this many queries

# Retry config
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 3  # seconds
_RETRY_JITTER = 0.2  # 20% random jitter

# Timeouts
_PAGE_LOAD_TIMEOUT = 30000  # ms
_RESULTS_TIMEOUT = 15000  # ms

# Regex for booking class availability: letter + digit (e.g., D9, D0)
_CLASS_PATTERN = re.compile(r"\b([A-Z])(\d)\b")

# Keyring service name
_KEYRING_SERVICE = "expertflyer.com"


class ScrapeError(Exception):
    """Error during ExpertFlyer scraping."""

    def __init__(self, message: str, error_type: str = "UNKNOWN") -> None:
        super().__init__(message)
        self.error_type = error_type


class SessionExpiredError(ScrapeError):
    """Session has expired, requiring re-login."""

    def __init__(self, message: str = "ExpertFlyer session expired") -> None:
        super().__init__(message, error_type="SESSION_EXPIRED")


def _get_credentials() -> tuple[str, str] | None:
    """Retrieve ExpertFlyer credentials from macOS Keychain."""
    try:
        import keyring

        username = keyring.get_password(_KEYRING_SERVICE, "username")
        password = keyring.get_password(_KEYRING_SERVICE, "password")
        if username and password:
            return username, password
    except Exception:
        pass
    return None


class ExpertFlyerScraper:
    """Scrape ExpertFlyer for D-class availability.

    Uses programmatic Auth0 login with credentials from macOS Keychain.
    Maintains a persistent browser context across multiple queries to
    keep the session alive.

    Usage:
        scraper = ExpertFlyerScraper()
        with scraper:
            result = scraper.check_availability("LHR", "HKG", date, "CX")

    Or for single queries (auto-manages lifecycle):
        scraper = ExpertFlyerScraper()
        result = scraper.check_availability("LHR", "HKG", date, "CX")
    """

    def __init__(self, session_path: Optional[str] = None) -> None:
        self._session_path = session_path  # Legacy: not used for login anymore
        self._last_call_time: float = 0
        self._query_count: int = 0
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

    def __enter__(self) -> "ExpertFlyerScraper":
        self._ensure_browser()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """Close browser and cleanup."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._context = None
        self._page = None
        self._logged_in = False

    def _ensure_browser(self) -> None:
        """Launch browser and context if not already running."""
        if self._page is not None:
            return

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = self._context.new_page()

    def _login(self) -> bool:
        """Programmatic Auth0 login using Keychain credentials."""
        creds = _get_credentials()
        if creds is None:
            logger.error(
                "No ExpertFlyer credentials. "
                "Run: rtw login expertflyer"
            )
            return False

        username, password = creds
        page = self._page

        logger.info("Logging in to ExpertFlyer...")
        page.goto(_LOGIN_URL, timeout=_PAGE_LOAD_TIMEOUT)
        time.sleep(3)

        if "auth.expertflyer.com" not in page.url:
            # Already logged in or unexpected page
            if "www.expertflyer.com" in page.url:
                self._logged_in = True
                return True
            return False

        # Fill Auth0 login form
        try:
            # Email field
            page.wait_for_selector(
                'input[name="email"], input[name="username"], input[type="email"]',
                timeout=10000,
            )
            email_input = (
                page.query_selector('input[name="email"]')
                or page.query_selector('input[name="username"]')
                or page.query_selector('input[type="email"]')
            )
            if not email_input:
                logger.error("Email input not found on Auth0 page")
                return False

            email_input.fill(username)

            # Click continue (Auth0 may split email/password screens)
            submit = page.query_selector('button[type="submit"]')
            if submit:
                submit.click()
                time.sleep(2)

            # Password field
            pwd_input = (
                page.query_selector('input[name="password"]')
                or page.query_selector('input[type="password"]')
            )
            if not pwd_input:
                logger.error("Password input not found")
                return False

            pwd_input.fill(password)

            # Submit login
            submit = page.query_selector('button[type="submit"]')
            if submit:
                submit.click()
                time.sleep(5)

            # Verify login succeeded
            if "www.expertflyer.com" in page.url:
                self._logged_in = True
                logger.info("ExpertFlyer login successful")
                return True

            # May still be on auth page with redirect pending
            time.sleep(3)
            if "www.expertflyer.com" in page.url:
                self._logged_in = True
                logger.info("ExpertFlyer login successful (delayed redirect)")
                return True

            logger.error("Login failed. URL: %s", page.url[:80])
            return False

        except Exception as exc:
            logger.error("Login error: %s", exc)
            return False

    def _ensure_logged_in(self) -> None:
        """Ensure we have a browser and are logged in."""
        self._ensure_browser()
        if not self._logged_in:
            if not self._login():
                raise SessionExpiredError("Failed to log in to ExpertFlyer")

    def _check_session_expired(self, page) -> None:
        """Raise SessionExpiredError if redirected to login."""
        url = page.url
        if "auth.expertflyer.com" in url or "/login" in url:
            self._logged_in = False
            raise SessionExpiredError()

    def _build_results_url(
        self,
        origin: str,
        dest: str,
        date: datetime.date,
        booking_class: str = "D",
        carrier: str = "",
    ) -> str:
        """Construct the ExpertFlyer results URL directly."""
        dt = date.strftime("%Y-%m-%dT00:00")
        params = {
            "origin": origin.upper(),
            "destination": dest.upper(),
            "departureDateTime": dt,
            "alliance": "none",
            "airLineCodes": carrier.upper() if carrier else "",
            "excludeCodeshares": "false",
            "classFilter": booking_class.upper(),
            "pcc": "USA (Default)",
            "resultsDisplay": "single",
        }
        qs = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        return f"{_RESULTS_URL}?{qs}"

    def _rate_limit_wait(self) -> None:
        """Enforce minimum interval between queries."""
        elapsed = time.time() - self._last_call_time
        if elapsed < _MIN_QUERY_INTERVAL:
            wait = _MIN_QUERY_INTERVAL - elapsed + random.uniform(0.5, 2.0)
            logger.debug("Rate limit: waiting %.1fs", wait)
            time.sleep(wait)

    def check_availability(
        self,
        origin: str,
        dest: str,
        date: datetime.date,
        carrier: str = "",
        booking_class: str = "D",
    ) -> Optional["DClassResult"]:
        """Check D-class availability for a route on a date.

        Logs in automatically if needed. Reuses the browser context
        across multiple calls for efficiency.

        Args:
            origin: 3-letter IATA origin airport.
            dest: 3-letter IATA destination airport.
            date: Target flight date.
            carrier: 2-letter airline code (empty = all carriers).
            booking_class: Booking class to check (default "D").

        Returns:
            DClassResult with availability info, or None if login failed.

        Raises:
            SessionExpiredError: If login fails or session expires mid-batch.
            ScrapeError: On parse or navigation errors (after retries).
        """
        from rtw.verify.models import DClassResult, DClassStatus

        # Check credentials exist before starting
        if _get_credentials() is None and not self._session_path:
            logger.info("No ExpertFlyer credentials configured")
            return None

        self._rate_limit_wait()
        self._query_count += 1
        if self._query_count == _DAILY_SOFT_LIMIT:
            logger.warning(
                "ExpertFlyer soft limit reached (%d queries). "
                "Consider spacing out checks.",
                _DAILY_SOFT_LIMIT,
            )

        url = self._build_results_url(origin, dest, date, booking_class, carrier)
        last_error: Optional[Exception] = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._ensure_logged_in()
                result = self._fetch_and_parse(
                    url, origin, dest, date, carrier, booking_class
                )
                self._last_call_time = time.time()
                return result
            except SessionExpiredError:
                if attempt < _MAX_RETRIES:
                    # Try re-login once
                    logger.warning("Session expired, attempting re-login...")
                    self._logged_in = False
                    continue
                raise
            except ScrapeError as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    jitter = delay * random.uniform(-_RETRY_JITTER, _RETRY_JITTER)
                    wait = delay + jitter
                    logger.warning(
                        "ExpertFlyer attempt %d/%d failed: %s. Retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BASE_DELAY)

        # All retries exhausted
        self._last_call_time = time.time()
        return DClassResult(
            status=DClassStatus.ERROR,
            seats=0,
            carrier=carrier or "??",
            origin=origin,
            destination=dest,
            target_date=date,
            error_message=str(last_error),
        )

    def _fetch_and_parse(
        self,
        url: str,
        origin: str,
        dest: str,
        date: datetime.date,
        carrier: str,
        booking_class: str,
    ) -> "DClassResult":
        """Navigate to results URL and parse the availability table.

        Uses the persistent page — no new browser launch per call.
        """
        page = self._page

        logger.info("ExpertFlyer: fetching %s→%s on %s", origin, dest, date)
        page.goto(url, timeout=_PAGE_LOAD_TIMEOUT)

        # Wait for table or detect session expiry
        time.sleep(2)
        self._check_session_expired(page)

        # Wait for results table
        try:
            page.wait_for_selector(
                "table.w-full.bg-white.shadow-md",
                timeout=_RESULTS_TIMEOUT,
            )
        except Exception:
            # Check if session expired during load
            self._check_session_expired(page)
            raise ScrapeError(
                f"Results table not found for {origin}→{dest}",
                error_type="PARSE_ERROR",
            )

        # Parse the results
        return self._parse_results_table(
            page, origin, dest, date, carrier, booking_class
        )

    def _parse_results_table(
        self,
        page,
        origin: str,
        dest: str,
        date: datetime.date,
        carrier: str,
        booking_class: str,
    ) -> "DClassResult":
        """Parse the ExpertFlyer results table for per-flight D-class data."""
        from rtw.verify.models import DClassResult, DClassStatus, FlightAvailability

        flights: list[FlightAvailability] = []

        try:
            rows = page.query_selector_all("tr.hover\\:bg-sky-50")
            for row in rows:
                text = row.evaluate("el => (el.innerText || '')")

                # Extract D-class seats
                d_match = re.search(rf"\b{booking_class}(\d)\b", text)
                if d_match is None:
                    continue
                seats = int(d_match.group(1))

                # Extract carrier + flight number (carrier is first field in row)
                flight_carrier = None
                flight_num = None
                fn_match = re.match(r"\s*([A-Z\d]{2})\s*\n\s*(\d{1,4})\b", text)
                if fn_match:
                    flight_carrier = fn_match.group(1)
                    flight_num = f"{fn_match.group(1)}{fn_match.group(2)}"

                # Extract stops (digit after flight number area)
                stops = 0
                stops_match = re.search(r"\b(\d)\s*\n", text)
                if stops_match:
                    stops = int(stops_match.group(1))

                # Extract departure/arrival times
                times = re.findall(
                    r"(\d{2}/\d{2}/\d{2}\s+\d{1,2}:\d{2}\s+[AP]M)", text
                )

                # Extract airports (3-letter codes in the row)
                airports = re.findall(r"\b([A-Z]{3})\b", text)
                # Filter to likely IATA codes (exclude common non-airport 3-letter combos)
                iata_airports = [
                    a for a in airports
                    if a not in ("Daily", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
                ]

                # Extract aircraft type
                aircraft = None
                ac_match = re.search(r"\b(3\d{2}|7[2-8]\w|A\d{2}\w?|E\d{2})\b", text)
                if ac_match:
                    aircraft = ac_match.group(1)

                flights.append(FlightAvailability(
                    carrier=flight_carrier or carrier or None,
                    flight_number=flight_num,
                    origin=iata_airports[0] if len(iata_airports) > 0 else origin,
                    destination=iata_airports[1] if len(iata_airports) > 1 else dest,
                    depart_time=times[0] if len(times) > 0 else None,
                    arrive_time=times[1] if len(times) > 1 else None,
                    aircraft=aircraft,
                    seats=seats,
                    booking_class=booking_class,
                    stops=stops,
                ))

        except Exception as exc:
            logger.warning("Per-row extraction failed, falling back to body text: %s", exc)

        # Fallback: if per-row extraction got nothing, use body-text regex
        if not flights:
            body_text = page.evaluate("() => document.body.innerText")
            pattern = re.compile(rf"\b{booking_class}(\d)\b")
            matches = pattern.findall(body_text)

            if not matches:
                return DClassResult(
                    status=DClassStatus.NOT_AVAILABLE,
                    seats=0,
                    carrier=carrier or "??",
                    origin=origin,
                    destination=dest,
                    target_date=date,
                )

            seat_counts = [int(m) for m in matches]
            best_seats = max(seat_counts)
            flight_number = self._extract_flight_number(page, carrier)

            status = DClassStatus.AVAILABLE if best_seats > 0 else DClassStatus.NOT_AVAILABLE
            return DClassResult(
                status=status,
                seats=best_seats,
                flight_number=flight_number,
                carrier=carrier or "??",
                origin=origin,
                destination=dest,
                target_date=date,
            )

        # Deduplicate flights by flight_number + depart_time
        seen = set()
        unique_flights = []
        for f in flights:
            key = (f.flight_number, f.depart_time)
            if key not in seen:
                seen.add(key)
                unique_flights.append(f)
        flights = unique_flights

        # Build result from per-flight data
        best_seats = max(f.seats for f in flights)
        # Set flight_number to the best-D-class flight
        best_flight = max(flights, key=lambda f: (f.seats, -(len(f.depart_time or ""))))
        flight_number = best_flight.flight_number

        status = DClassStatus.AVAILABLE if best_seats > 0 else DClassStatus.NOT_AVAILABLE

        return DClassResult(
            status=status,
            seats=best_seats,
            flight_number=flight_number,
            carrier=carrier or "??",
            origin=origin,
            destination=dest,
            target_date=date,
            flights=flights,
        )

    def _extract_flight_number(self, page, carrier: str) -> Optional[str]:
        """Try to extract the first flight number from results."""
        try:
            rows = page.query_selector_all("tr.hover\\:bg-sky-50")
            if rows:
                text = rows[0].evaluate(
                    "el => (el.innerText || '').substring(0, 100)"
                )
                if carrier:
                    match = re.search(
                        rf"\b{re.escape(carrier)}\s*(\d{{1,4}})\b", text
                    )
                    if match:
                        return f"{carrier}{match.group(1)}"
                match = re.search(r"\b([A-Z]{2})\s*(\d{1,4})\b", text)
                if match:
                    return f"{match.group(1)}{match.group(2)}"
        except Exception:
            pass
        return None


def parse_availability_html(
    html: str, booking_class: str = "D"
) -> list[dict]:
    """Parse ExpertFlyer results HTML for availability data.

    Standalone parser for testing with HTML fixtures.

    Returns list of dicts with: carrier, flight_number, origin, destination,
    depart_time, arrive_time, aircraft, frequency, reliability, seats.
    """
    results = []
    tbody_pattern = re.compile(
        r"<tbody[^>]*table-custom-hover-group[^>]*>(.*?)</tbody>",
        re.DOTALL,
    )
    row_pattern = re.compile(
        r"<tr[^>]*hover:bg-sky-50[^>]*>(.*?)</tr>",
        re.DOTALL,
    )

    for tbody_match in tbody_pattern.finditer(html):
        tbody_html = tbody_match.group(1)

        for row_match in row_pattern.finditer(tbody_html):
            row_html = row_match.group(1)
            row_text = re.sub(r"<[^>]+>", " ", row_html)
            row_text = re.sub(r"\s+", " ", row_text).strip()

            class_pattern = re.compile(rf"\b{booking_class}(\d)\b")
            class_match = class_pattern.search(row_text)
            seats = int(class_match.group(1)) if class_match else None

            carrier_match = re.search(r"\b([A-Z]{2})\b", row_text)
            flight_match = re.search(r"\b([A-Z]{2})\s+(\d{1,4})\b", row_text)

            airports = re.findall(
                r'cursor-pointer text-sky-600[^>]*>([A-Z]{3})<', row_html
            )

            times = re.findall(
                r"(\d{2}/\d{2}/\d{2}\s+\d{1,2}:\d{2}\s+[AP]M)", row_text
            )

            aircraft_match = re.search(r"\b(\d{2}[A-Z0-9]|[A-Z]\d{2})\b", row_text)

            result = {
                "carrier": carrier_match.group(1) if carrier_match else None,
                "flight_number": (
                    f"{flight_match.group(1)}{flight_match.group(2)}"
                    if flight_match
                    else None
                ),
                "origin": airports[0] if len(airports) > 0 else None,
                "destination": airports[1] if len(airports) > 1 else None,
                "depart_time": times[0] if len(times) > 0 else None,
                "arrive_time": times[1] if len(times) > 1 else None,
                "aircraft": aircraft_match.group(1) if aircraft_match else None,
                "seats": seats,
                "booking_class": booking_class,
            }
            results.append(result)

    return results
