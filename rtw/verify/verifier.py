"""Availability verification orchestrator.

Coordinates the scraper, cache, and progress reporting to verify
award class availability across all flown segments of an itinerary option.
Uses per-carrier booking class resolution (AA=H, others=D for business).
"""

import logging
import time
from typing import Optional

from rtw.carriers import get_booking_class
from rtw.models import CabinClass
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
    """Verify award class availability for itinerary segments.

    Checks each flown segment against ExpertFlyer, using the cache
    to avoid redundant queries. Surface segments are skipped.

    Resolves booking class per carrier (AA=H, others=D for business)
    unless an explicit override is provided.
    """

    def __init__(
        self,
        scraper: ExpertFlyerScraper,
        cache: Optional[ScrapeCache] = None,
        booking_class: Optional[str] = None,
        cabin: CabinClass = CabinClass.BUSINESS,
    ) -> None:
        self.scraper = scraper
        self.cache = cache or ScrapeCache()
        self._booking_class_override = booking_class
        self.cabin = cabin
        self._session_expired = False

    def _get_segment_booking_class(self, seg: SegmentVerification) -> str:
        """Resolve the booking class for a segment.

        If an override was set, use it for all segments.
        Otherwise, look up per carrier from carriers.yaml.
        """
        if self._booking_class_override is not None:
            return self._booking_class_override
        return get_booking_class(seg.carrier, self.cabin)

    def _cache_key(self, seg: SegmentVerification) -> str:
        """Build cache key for a segment."""
        bc = self._get_segment_booking_class(seg)
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
                    booking_class=self._get_segment_booking_class(seg),
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

            # Call scraper
            try:
                seg_bc = self._get_segment_booking_class(seg)
                start = time.time()
                dclass = self.scraper.check_availability(
                    origin=seg.origin,
                    dest=seg.destination,
                    date=seg.target_date,
                    carrier=seg.carrier or "",
                    booking_class=seg_bc,
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
                    dclass.booking_class = seg_bc
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
                        booking_class=seg_bc,
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
                    booking_class=self._get_segment_booking_class(seg),
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
                    booking_class=self._get_segment_booking_class(seg),
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
