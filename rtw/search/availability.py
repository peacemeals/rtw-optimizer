"""Availability checking for RTW itinerary candidates."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable, Optional

from rtw.models import SegmentType
from rtw.scraper.cache import ScrapeCache
from rtw.scraper.google_flights import SearchBackend
from rtw.search.models import (
    AvailabilityStatus,
    ScoredCandidate,
    SearchQuery,
    SegmentAvailability,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, dict, Optional[SegmentAvailability]], None]


class AvailabilityChecker:
    """Checks flight availability for candidate itinerary segments."""

    def __init__(self, cache: Optional[ScrapeCache] = None, cabin: str = "business",
                 max_stops: Optional[int] = None,
                 backend: SearchBackend = SearchBackend.AUTO):
        self._cache = cache or ScrapeCache()
        self._cabin = cabin
        self._max_stops = max_stops
        self._backend = backend

    def check_candidate(
        self,
        candidate: ScoredCandidate,
        query: SearchQuery,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> None:
        """Check availability for all segments. Updates candidate in-place."""
        segments = candidate.candidate.itinerary.segments
        route_segs = candidate.candidate.route_segments

        # Assign dates
        dates = self._assign_dates(candidate, query)

        confirmed = 0
        flown_total = 0

        for i, seg in enumerate(segments):
            seg_info = {
                "from": seg.from_airport,
                "to": seg.to_airport,
                "carrier": seg.carrier,
            }

            if seg.type == SegmentType.SURFACE:
                result = SegmentAvailability(status=AvailabilityStatus.AVAILABLE)
            else:
                flown_total += 1
                seg_date = dates[i] if i < len(dates) else None
                result = self._check_segment(
                    seg.from_airport, seg.to_airport, seg_date, self._cabin
                )
                if result.status == AvailabilityStatus.AVAILABLE:
                    confirmed += 1

            # Update route segment availability
            if i < len(route_segs):
                route_segs[i].availability = result

            if progress_cb:
                progress_cb(i, len(segments), seg_info, result)

        # Update availability percentage
        if flown_total > 0:
            candidate.availability_pct = (confirmed / flown_total) * 100
        else:
            candidate.availability_pct = 100.0

    def _check_segment(
        self,
        from_apt: str,
        to_apt: str,
        seg_date: Optional[date],
        cabin: str,
    ) -> SegmentAvailability:
        """Check availability for a single segment. Cache-first."""
        date_str = seg_date.isoformat() if seg_date else "nodate"
        cache_key = f"avail_{from_apt}_{to_apt}_{date_str}_{cabin}"

        # Check cache
        cached = self._cache.get(cache_key)
        if cached is not None:
            return SegmentAvailability(
                status=AvailabilityStatus(cached.get("status", "unknown")),
                price_usd=cached.get("price_usd"),
                carrier=cached.get("carrier"),
                date=seg_date,
                source=cached.get("source"),
                flight_number=cached.get("flight_number"),
                duration_minutes=cached.get("duration_minutes"),
            )

        if seg_date is None:
            return SegmentAvailability(status=AvailabilityStatus.UNKNOWN)

        result = self._search_with_cascade(from_apt, to_apt, seg_date, cabin)

        if result is not None:
            avail = SegmentAvailability(
                status=AvailabilityStatus.AVAILABLE,
                price_usd=result.price_usd,
                carrier=result.carrier,
                date=seg_date,
                stops=result.stops,
                source=result.source,
                flight_number=result.flight_number,
                duration_minutes=result.duration_minutes,
            )
            self._cache.set(cache_key, {
                "status": avail.status.value,
                "price_usd": avail.price_usd,
                "carrier": avail.carrier,
                "source": avail.source,
                "flight_number": avail.flight_number,
                "duration_minutes": avail.duration_minutes,
            }, ttl_hours=6)
            return avail

        return SegmentAvailability(status=AvailabilityStatus.UNKNOWN, date=seg_date)

    def _search_with_cascade(self, from_apt, to_apt, seg_date, cabin):
        """Search for flights using configured backend(s)."""
        backend = self._backend

        if backend == SearchBackend.AUTO:
            search_fns = self._auto_cascade_fns()
        elif backend == SearchBackend.SERPAPI:
            search_fns = [("serpapi", self._try_serpapi)]
        elif backend == SearchBackend.FAST_FLIGHTS:
            search_fns = [("fast-flights", self._try_fast_flights)]
        elif backend == SearchBackend.PLAYWRIGHT:
            search_fns = [("playwright", self._try_playwright)]
        else:
            search_fns = self._auto_cascade_fns()

        for name, fn in search_fns:
            try:
                result = fn(from_apt, to_apt, seg_date, cabin)
                if result is not None:
                    return result
            except Exception as exc:
                if backend != SearchBackend.AUTO:
                    raise
                logger.debug("Cascade %s failed for %s-%s: %s", name, from_apt, to_apt, exc)

        return None

    def _auto_cascade_fns(self):
        """Build cascade function list for AUTO mode."""
        fns = []
        from rtw.scraper.serpapi_flights import serpapi_available
        if serpapi_available():
            fns.append(("serpapi", self._try_serpapi))
        fns.append(("fast-flights", self._try_fast_flights))
        fns.append(("playwright", self._try_playwright))
        return fns

    def _try_serpapi(self, from_apt, to_apt, seg_date, cabin):
        from rtw.scraper.serpapi_flights import search_serpapi
        return search_serpapi(
            origin=from_apt, dest=to_apt, date=seg_date,
            cabin=cabin, max_stops=self._max_stops,
        )

    def _try_fast_flights(self, from_apt, to_apt, seg_date, cabin):
        from rtw.scraper.google_flights import search_fast_flights
        return search_fast_flights(from_apt, to_apt, seg_date, cabin)

    def _try_playwright(self, from_apt, to_apt, seg_date, cabin):
        from rtw.scraper.google_flights import search_playwright_sync
        return search_playwright_sync(
            from_apt, to_apt, seg_date, cabin, max_stops=self._max_stops,
        )

    def _assign_dates(
        self,
        candidate: ScoredCandidate,
        query: SearchQuery,
    ) -> list[Optional[date]]:
        """Assign approximate dates to segments within the date window."""
        segments = candidate.candidate.itinerary.segments
        dates: list[Optional[date]] = []
        current_date = query.date_from

        for seg in segments:
            if seg.type == SegmentType.SURFACE:
                dates.append(None)
            elif seg.type == SegmentType.TRANSIT:
                # Same day as previous segment
                dates.append(current_date)
            else:
                # Stopover — advance by 2-3 days
                dates.append(current_date)
                current_date = min(current_date + timedelta(days=3), query.date_to)

        return dates
