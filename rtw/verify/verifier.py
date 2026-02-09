"""D-class verification orchestrator.

Coordinates the scraper, cache, and progress reporting to verify
D-class availability across all flown segments of an itinerary option.
"""

import logging
import time
from pathlib import Path
from typing import Optional

import yaml

from rtw.scraper.cache import ScrapeCache
from rtw.scraper.expertflyer import ExpertFlyerScraper, SessionExpiredError
from rtw.verify.models import (
    DClassResult,
    DClassStatus,
    ProgressCallback,
    SegmentVerification,
    VerifyOption,
    VerifyResult,
)

logger = logging.getLogger(__name__)

_CACHE_TTL_HOURS = 24
_CACHE_KEY_PREFIX = "dclass"


class DClassVerifier:
    """Verify D-class availability for itinerary segments.

    Checks each flown segment against ExpertFlyer, using the cache
    to avoid redundant queries. Surface segments are skipped.
    """

    def __init__(
        self,
        scraper: ExpertFlyerScraper,
        cache: Optional[ScrapeCache] = None,
        booking_class: str = "D",
    ) -> None:
        self.scraper = scraper
        self.cache = cache or ScrapeCache()
        self.booking_class = booking_class
        self._session_expired = False

        # Load carrier data for per-carrier booking class lookup
        carriers_path = Path(__file__).parent.parent / "data" / "carriers.yaml"
        with open(carriers_path) as f:
            self._carriers: dict = yaml.safe_load(f)

    def _get_booking_class(self, carrier: str) -> str:
        """Look up the correct booking class for a carrier.

        Uses rtw_booking_class from carriers.yaml (e.g. AA -> H).
        Falls back to self.booking_class (default D) for unknown carriers.
        """
        if not carrier:
            return self.booking_class
        carrier_data = self._carriers.get(carrier.upper(), {})
        return carrier_data.get("rtw_booking_class", self.booking_class) or self.booking_class

    def _cache_key(self, seg: SegmentVerification) -> str:
        """Build cache key for a segment."""
        bc = self._get_booking_class(seg.carrier or "")
        return (
            f"{_CACHE_KEY_PREFIX}_{seg.carrier}_{seg.origin}_"
            f"{seg.destination}_{seg.target_date}_{bc}"
        )

    def _check_cache(self, seg: SegmentVerification) -> Optional[DClassResult]:
        """Look up cached result for a segment."""
        if self.cache is None:
            return None
        key = self._cache_key(seg)
        cached = self.cache.get(key)
        if cached is None:
            return None
        try:
            result = DClassResult.model_validate(cached)
            result.from_cache = True
            result.status = (
                DClassStatus.AVAILABLE
                if result.seats > 0
                else DClassStatus.NOT_AVAILABLE
            )
            return result
        except Exception:
            return None

    def _store_cache(self, seg: SegmentVerification, result: DClassResult) -> None:
        """Cache a D-class result."""
        if self.cache is None:
            return
        key = self._cache_key(seg)
        self.cache.set(key, result.model_dump(mode="json"), ttl_hours=_CACHE_TTL_HOURS)

    def verify_option(
        self,
        option: VerifyOption,
        progress_cb: Optional[ProgressCallback] = None,
        no_cache: bool = False,
    ) -> VerifyResult:
        """Verify D-class for all flown segments in one option.

        Surface segments are skipped (not sent to scraper).
        On SessionExpiredError, remaining segments are marked UNKNOWN.
        On individual segment errors, that segment is marked ERROR
        and verification continues.
        """
        result = VerifyResult(option_id=option.option_id, segments=[])

        for seg in option.segments:
            # Copy segment for result
            verified = seg.model_copy()

            if seg.segment_type == "SURFACE":
                result.segments.append(verified)
                if progress_cb:
                    progress_cb(len(result.segments), len(option.segments), verified)
                continue

            if self._session_expired:
                # Session died mid-batch — mark remaining as unknown
                verified.dclass = DClassResult(
                    status=DClassStatus.UNKNOWN,
                    seats=0,
                    carrier=seg.carrier or "??",
                    origin=seg.origin,
                    destination=seg.destination,
                    target_date=seg.target_date,
                    error_message="Session expired during batch",
                )
                result.segments.append(verified)
                if progress_cb:
                    progress_cb(len(result.segments), len(option.segments), verified)
                continue

            # Check cache first
            if not no_cache:
                cached = self._check_cache(seg)
                if cached is not None:
                    verified.dclass = cached
                    result.segments.append(verified)
                    if progress_cb:
                        progress_cb(
                            len(result.segments), len(option.segments), verified
                        )
                    continue

            # Call scraper with per-carrier booking class
            try:
                booking_class = self._get_booking_class(seg.carrier or "")
                start = time.time()
                dclass = self.scraper.check_availability(
                    origin=seg.origin,
                    dest=seg.destination,
                    date=seg.target_date,
                    carrier=seg.carrier or "",
                    booking_class=booking_class,
                )
                elapsed = time.time() - start
                logger.debug(
                    "ExpertFlyer check %s→%s: %s (%.1fs)",
                    seg.origin,
                    seg.destination,
                    dclass.display_code if dclass else "None",
                    elapsed,
                )

                if dclass:
                    verified.dclass = dclass
                    self._store_cache(seg, dclass)
                else:
                    verified.dclass = DClassResult(
                        status=DClassStatus.UNKNOWN,
                        seats=0,
                        carrier=seg.carrier or "??",
                        origin=seg.origin,
                        destination=seg.destination,
                        target_date=seg.target_date,
                        error_message="Scraper returned None (no session?)",
                    )

            except SessionExpiredError as exc:
                self._session_expired = True
                verified.dclass = DClassResult(
                    status=DClassStatus.UNKNOWN,
                    seats=0,
                    carrier=seg.carrier or "??",
                    origin=seg.origin,
                    destination=seg.destination,
                    target_date=seg.target_date,
                    error_message=str(exc),
                )
            except Exception as exc:
                verified.dclass = DClassResult(
                    status=DClassStatus.ERROR,
                    seats=0,
                    carrier=seg.carrier or "??",
                    origin=seg.origin,
                    destination=seg.destination,
                    target_date=seg.target_date,
                    error_message=str(exc),
                )

            result.segments.append(verified)
            if progress_cb:
                progress_cb(len(result.segments), len(option.segments), verified)

        return result

    def verify_batch(
        self,
        options: list[VerifyOption],
        progress_cb: Optional[ProgressCallback] = None,
        no_cache: bool = False,
    ) -> list[VerifyResult]:
        """Verify D-class for multiple itinerary options sequentially."""
        results = []
        for option in options:
            result = self.verify_option(option, progress_cb, no_cache)
            results.append(result)
        return results
