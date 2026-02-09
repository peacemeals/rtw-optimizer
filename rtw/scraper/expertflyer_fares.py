"""ExpertFlyer fare information scraper.

Scrapes RTW (oneworld Explorer) fare prices from ExpertFlyer's
Fare Information page.  Reuses an existing ExpertFlyerScraper's
browser session to avoid duplicate login.

URL pattern (origin = destination for RTW round-trip fares):
    /air/fare-information/results?origin=OSL&destination=OSL
    &startDate=2026-02-09&airLineCodes=AA&currency=USD
    &passengerType=ADT&filterResults=true&allFares=false

Supports querying multiple carriers per origin (one query each).
"""

from __future__ import annotations

import datetime
import logging
import re
import time
from typing import Optional
from urllib.parse import quote_plus

from pydantic import BaseModel, Field

from rtw.scraper.expertflyer import (
    ExpertFlyerScraper,
    ScrapeError,
    _EXPERTFLYER_BASE,
    _MIN_QUERY_INTERVAL,
    _PAGE_LOAD_TIMEOUT,
    _RESULTS_TIMEOUT,
)

logger = logging.getLogger(__name__)

_FARE_RESULTS_URL = f"{_EXPERTFLYER_BASE}/air/fare-information/results"

# RTW fare basis pattern: xONEn or xGLOBn (x=L/D/A, n=3-6)
_RTW_FARE_PATTERN = re.compile(r"^[LDA](ONE|GLOB)\d$")

# Default carriers to check for RTW fares
DEFAULT_RTW_CARRIERS = ["AA", "AS", "QR", "BA", "FJ", "RJ"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class FareInfo(BaseModel):
    """A single fare from ExpertFlyer fare information results."""

    fare_basis: str
    airline: str
    booking_class: str
    trip_type: str = ""
    fare_usd: float
    cabin: str = ""
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    min_stay: Optional[str] = None
    max_stay: Optional[str] = None
    advance_purchase: Optional[str] = None

    @property
    def fare_family(self) -> str:
        """Extract fare family: DONE, AONE, LONE, DGLOB, etc."""
        m = re.match(r"([LDA](?:ONE|GLOB))", self.fare_basis)
        return m.group(1) if m else self.fare_basis

    @property
    def continent_count(self) -> Optional[int]:
        """Extract continent count (3-6) from fare basis."""
        m = re.search(r"(\d)$", self.fare_basis)
        return int(m.group(1)) if m else None

    @property
    def is_rtw(self) -> bool:
        """Whether this is an RTW fare (xONE or xGLOB pattern)."""
        return bool(_RTW_FARE_PATTERN.match(self.fare_basis))


class OriginFareResult(BaseModel):
    """Fare results for a single origin city across one or more carriers."""

    origin: str = Field(min_length=3, max_length=3)
    carriers_queried: list[str] = Field(default_factory=list)
    currency: str = "USD"
    query_date: datetime.date = Field(
        default_factory=lambda: datetime.date.today()
    )
    fares: list[FareInfo] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)

    @property
    def rtw_fares(self) -> list[FareInfo]:
        """Only RTW fares (xONE/xGLOB patterns)."""
        return [f for f in self.fares if f.is_rtw]

    @property
    def done_fares(self) -> list[FareInfo]:
        """DONE (business) fares sorted by fare basis."""
        return sorted(
            [f for f in self.fares if f.fare_basis.startswith("DONE")],
            key=lambda f: f.fare_basis,
        )

    @property
    def aone_fares(self) -> list[FareInfo]:
        """AONE (first) fares sorted by fare basis."""
        return sorted(
            [f for f in self.fares if f.fare_basis.startswith("AONE")],
            key=lambda f: f.fare_basis,
        )

    @property
    def lone_fares(self) -> list[FareInfo]:
        """LONE (economy) fares sorted by fare basis."""
        return sorted(
            [f for f in self.fares if f.fare_basis.startswith("LONE")],
            key=lambda f: f.fare_basis,
        )

    def get_fare(self, fare_basis: str) -> Optional[FareInfo]:
        """Look up a specific fare basis. Returns cheapest if multiple carriers file it."""
        matches = [f for f in self.fares if f.fare_basis == fare_basis]
        if not matches:
            return None
        return min(matches, key=lambda f: f.fare_usd)

    def get_fare_by_carrier(self, fare_basis: str, carrier: str) -> Optional[FareInfo]:
        """Look up a fare for a specific carrier."""
        for f in self.fares:
            if f.fare_basis == fare_basis and f.airline == carrier:
                return f
        return None


class FareComparisonResult(BaseModel):
    """Comparison of RTW fares across multiple origin cities."""

    origins: list[OriginFareResult] = Field(default_factory=list)
    carriers: list[str] = Field(default_factory=list)
    currency: str = "USD"

    def cheapest_for(self, fare_basis: str) -> Optional[OriginFareResult]:
        """Find the origin with the cheapest fare for a given fare basis."""
        best = None
        best_price = float("inf")
        for o in self.origins:
            fare = o.get_fare(fare_basis)
            if fare and fare.fare_usd < best_price:
                best = o
                best_price = fare.fare_usd
        return best

    def ranking_for(self, fare_basis: str) -> list[tuple[str, float, str]]:
        """Rank origins by price for a fare basis.

        Returns (origin, price, carrier) triples sorted by price.
        """
        triples = []
        for o in self.origins:
            fare = o.get_fare(fare_basis)
            if fare:
                triples.append((o.origin, fare.fare_usd, fare.airline))
        return sorted(triples, key=lambda t: t[1])


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class ExpertFlyerFareScraper:
    """Scrape fare information from ExpertFlyer.

    Reuses an existing ExpertFlyerScraper instance for browser/login management.
    Supports querying multiple carriers per origin.

    Usage:
        with ExpertFlyerScraper() as scraper:
            fare_scraper = ExpertFlyerFareScraper(scraper)
            result = fare_scraper.search_fares("OSL", carriers=["AA", "QR"])
    """

    def __init__(self, scraper: ExpertFlyerScraper) -> None:
        self._scraper = scraper

    def _build_fare_url(
        self,
        origin: str,
        carrier: str,
        currency: str = "USD",
        date: Optional[datetime.date] = None,
    ) -> str:
        """Construct ExpertFlyer fare information URL.

        For RTW fares, origin = destination (round-the-world).
        """
        if date is None:
            date = datetime.date.today()
        dt = date.strftime("%Y-%m-%d")
        params = {
            "origin": origin.upper(),
            "destination": origin.upper(),  # RTW: same origin/dest
            "startDate": dt,
            "airLineCodes": carrier.upper(),
            "currency": currency.upper(),
            "passengerType": "ADT",
            "filterResults": "true",
            "allFares": "false",
        }
        qs = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        return f"{_FARE_RESULTS_URL}?{qs}"

    def _search_single_carrier(
        self,
        origin: str,
        carrier: str,
        currency: str = "USD",
        date: Optional[datetime.date] = None,
    ) -> tuple[list[FareInfo], Optional[str]]:
        """Search fares for a single origin+carrier combination.

        Returns (fares_list, error_message_or_none).
        """
        if date is None:
            date = datetime.date.today()

        self._scraper._ensure_logged_in()

        # Rate limiting
        elapsed = time.time() - self._scraper._last_call_time
        if elapsed < _MIN_QUERY_INTERVAL:
            wait = _MIN_QUERY_INTERVAL - elapsed + 1.0
            time.sleep(wait)

        url = self._build_fare_url(origin, carrier, currency, date)

        try:
            page = self._scraper._page
            logger.info("ExpertFlyer fares: %s on %s", origin, carrier)
            page.goto(url, timeout=_PAGE_LOAD_TIMEOUT)
            time.sleep(2)

            self._scraper._check_session_expired(page)

            try:
                page.wait_for_selector("table", timeout=_RESULTS_TIMEOUT)
            except Exception:
                self._scraper._check_session_expired(page)
                body = page.evaluate("() => document.body.innerText")
                if "no fares" in body.lower() or "no results" in body.lower():
                    return [], None
                raise ScrapeError(
                    f"Fare table not found for {origin} on {carrier}",
                    error_type="PARSE_ERROR",
                )

            self._scraper._last_call_time = time.time()
            self._scraper._query_count += 1

            fares = self._parse_fare_table(page, carrier)
            return fares, None

        except ScrapeError:
            raise
        except Exception as exc:
            self._scraper._last_call_time = time.time()
            return [], str(exc)

    def search_fares(
        self,
        origin: str,
        carriers: Optional[list[str]] = None,
        currency: str = "USD",
        date: Optional[datetime.date] = None,
    ) -> OriginFareResult:
        """Search for RTW fares from an origin city on multiple carriers.

        Args:
            origin: 3-letter IATA airport code.
            carriers: List of 2-letter airline codes (default: DEFAULT_RTW_CARRIERS).
            currency: Currency for fare display (default USD).
            date: Date for fare validity (default today).

        Returns:
            OriginFareResult with fares from all queried carriers.
        """
        if carriers is None:
            carriers = DEFAULT_RTW_CARRIERS
        if date is None:
            date = datetime.date.today()

        all_fares: list[FareInfo] = []
        errors: dict[str, str] = {}

        for carrier in carriers:
            try:
                fares, error = self._search_single_carrier(
                    origin, carrier, currency, date
                )
                all_fares.extend(fares)
                if error:
                    errors[carrier] = error
            except Exception as exc:
                errors[carrier] = str(exc)

        # Deduplicate: if same fare basis appears on multiple carriers,
        # keep the cheapest
        return OriginFareResult(
            origin=origin.upper(),
            carriers_queried=[c.upper() for c in carriers],
            currency=currency.upper(),
            query_date=date,
            fares=all_fares,
            errors=errors,
        )

    def _parse_fare_table(self, page, carrier: str) -> list[FareInfo]:
        """Parse the ExpertFlyer fare information results table."""
        fares: list[FareInfo] = []

        try:
            rows = page.query_selector_all("table tbody tr")
            if not rows:
                rows = page.query_selector_all("tr.hover\\:bg-sky-50")

            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) < 5:
                    continue

                cell_texts = []
                for cell in cells:
                    text = cell.evaluate("el => (el.innerText || '').trim()")
                    cell_texts.append(text)

                fare_basis = cell_texts[0].strip() if len(cell_texts) > 0 else ""
                if not fare_basis:
                    continue

                airline = cell_texts[1].strip() if len(cell_texts) > 1 else carrier
                booking_class = cell_texts[2].strip() if len(cell_texts) > 2 else ""
                trip_type = cell_texts[3].strip() if len(cell_texts) > 3 else ""
                fare_text = cell_texts[4].strip() if len(cell_texts) > 4 else "0"
                fare_usd = self._parse_fare_amount(fare_text)
                cabin = cell_texts[5].strip() if len(cell_texts) > 5 else ""
                effective = cell_texts[6].strip() if len(cell_texts) > 6 else None
                expiration = cell_texts[7].strip() if len(cell_texts) > 7 else None
                min_max_stay = cell_texts[8].strip() if len(cell_texts) > 8 else None
                advance = cell_texts[9].strip() if len(cell_texts) > 9 else None

                fares.append(FareInfo(
                    fare_basis=fare_basis,
                    airline=airline,
                    booking_class=booking_class,
                    trip_type=trip_type,
                    fare_usd=fare_usd,
                    cabin=cabin,
                    effective_date=effective or None,
                    expiration_date=expiration or None,
                    min_stay=min_max_stay,
                    advance_purchase=advance or None,
                ))

        except Exception as exc:
            logger.warning("Fare table parse error: %s", exc)
            fares = self._parse_fare_body_text(page, carrier)

        return fares

    def _parse_fare_body_text(self, page, carrier: str) -> list[FareInfo]:
        """Fallback parser using body text regex."""
        fares: list[FareInfo] = []
        try:
            body = page.evaluate("() => document.body.innerText")
            pattern = re.compile(
                r"([LDA](?:ONE|GLOB)\d)\s+"
                r"(\w{2})\s+"
                r"([A-Z])\s+"
                r"(\w+)\s+"
                r"\$?([\d,]+\.?\d*)"
            )
            for m in pattern.finditer(body):
                fare_usd = float(m.group(5).replace(",", ""))
                fares.append(FareInfo(
                    fare_basis=m.group(1),
                    airline=m.group(2),
                    booking_class=m.group(3),
                    trip_type=m.group(4),
                    fare_usd=fare_usd,
                ))
        except Exception as exc:
            logger.warning("Body text fallback failed: %s", exc)
        return fares

    @staticmethod
    def _parse_fare_amount(text: str) -> float:
        """Parse a fare amount string like '$5,957.88' or '5957.88'."""
        cleaned = re.sub(r"[^\d.]", "", text)
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def search_multiple_origins(
        self,
        origins: list[str],
        carriers: Optional[list[str]] = None,
        currency: str = "USD",
        progress_cb=None,
    ) -> FareComparisonResult:
        """Search fares across multiple origin cities and carriers.

        Args:
            origins: List of IATA airport codes.
            carriers: Carrier codes to check (default: DEFAULT_RTW_CARRIERS).
            currency: Currency for fare display.
            progress_cb: Optional callback(current, total, origin, result).

        Returns:
            FareComparisonResult with all origins compared.
        """
        if carriers is None:
            carriers = DEFAULT_RTW_CARRIERS

        comparison = FareComparisonResult(
            carriers=[c.upper() for c in carriers],
            currency=currency.upper(),
        )

        for i, origin in enumerate(origins):
            result = self.search_fares(origin, carriers, currency)
            comparison.origins.append(result)

            if progress_cb:
                progress_cb(i + 1, len(origins), origin, result)

        return comparison
