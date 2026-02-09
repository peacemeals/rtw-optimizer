"""Tests for availability checking."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from rtw.models import (
    CabinClass,
    Itinerary,
    Segment,
    SegmentType,
    Ticket,
    TicketType,
)
from rtw.scraper.cache import ScrapeCache
from rtw.scraper.google_flights import FlightPrice
from rtw.search.availability import AvailabilityChecker
from rtw.search.models import (
    AvailabilityStatus,
    CandidateItinerary,
    Direction,
    RouteSegment,
    ScoredCandidate,
    SearchQuery,
)

FUTURE = date.today() + timedelta(days=60)
FUTURE_END = date.today() + timedelta(days=120)


def _make_query() -> SearchQuery:
    return SearchQuery(
        cities=["LHR", "NRT", "JFK"],
        origin="SYD",
        date_from=FUTURE,
        date_to=FUTURE_END,
        cabin=CabinClass.BUSINESS,
        ticket_type=TicketType.DONE3,
    )


def _make_candidate(num_segs=5, surface_indices=None) -> ScoredCandidate:
    surface_indices = surface_indices or set()
    segs = []
    route_segs = []
    for i in range(num_segs):
        st = SegmentType.SURFACE if i in surface_indices else SegmentType.STOPOVER
        segs.append(Segment(**{"from": "AAA", "to": "BBB", "carrier": "AA", "type": st.value}))
        route_segs.append(RouteSegment(from_airport="AAA", to_airport="BBB", carrier="AA", segment_type=st))

    itin = Itinerary(
        ticket=Ticket(type=TicketType.DONE3, cabin=CabinClass.BUSINESS, origin="SYD"),
        segments=segs,
    )
    cand = CandidateItinerary(
        itinerary=itin, direction=Direction.EASTBOUND, route_segments=route_segs
    )
    return ScoredCandidate(candidate=cand)


@pytest.fixture
def tmp_cache(tmp_path):
    return ScrapeCache(cache_dir=tmp_path, default_ttl_hours=1)


class TestCoreAvailability:
    @patch("rtw.scraper.google_flights.search_fast_flights")
    def test_all_segments_checked(self, mock_search, tmp_cache):
        mock_search.return_value = FlightPrice(
            origin="AAA", dest="BBB", carrier="AA", price_usd=500, cabin="business"
        )
        checker = AvailabilityChecker(cache=tmp_cache)
        cand = _make_candidate(num_segs=3)
        query = _make_query()
        checker.check_candidate(cand, query)

        for rs in cand.candidate.route_segments:
            assert rs.availability is not None

    @patch("rtw.scraper.google_flights.search_fast_flights")
    def test_surface_auto_available(self, mock_search, tmp_cache):
        mock_search.return_value = None
        checker = AvailabilityChecker(cache=tmp_cache)
        cand = _make_candidate(num_segs=3, surface_indices={1})
        query = _make_query()
        checker.check_candidate(cand, query)

        assert cand.candidate.route_segments[1].availability.status == AvailabilityStatus.AVAILABLE
        # Surface should not trigger scraper for that segment

    @patch("rtw.scraper.google_flights.search_fast_flights")
    def test_availability_pct_calculated(self, mock_search, tmp_cache):
        # 2 available, 1 unknown
        call_count = [0]
        def _mock_search(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                return FlightPrice(origin="A", dest="B", carrier="AA", price_usd=100, cabin="business")
            return None

        mock_search.side_effect = _mock_search
        checker = AvailabilityChecker(cache=tmp_cache)
        cand = _make_candidate(num_segs=3)
        query = _make_query()
        checker.check_candidate(cand, query)

        # 2 out of 3 confirmed
        assert abs(cand.availability_pct - 66.7) < 1


class TestProgressCallback:
    @patch("rtw.scraper.google_flights.search_fast_flights", return_value=None)
    def test_progress_called_per_segment(self, mock_search, tmp_cache):
        calls = []
        def cb(idx, total, seg_info, result):
            calls.append((idx, total))

        checker = AvailabilityChecker(cache=tmp_cache)
        cand = _make_candidate(num_segs=4)
        query = _make_query()
        checker.check_candidate(cand, query, progress_cb=cb)

        assert len(calls) == 4
        assert calls[0] == (0, 4)
        assert calls[3] == (3, 4)


class TestCacheBehavior:
    @patch("rtw.scraper.google_flights.search_fast_flights")
    def test_cache_hit_avoids_scraper(self, mock_search, tmp_cache):
        # Pre-populate cache
        tmp_cache.set(f"avail_AAA_BBB_{FUTURE.isoformat()}_business", {
            "status": "available", "price_usd": 500, "carrier": "AA"
        })

        checker = AvailabilityChecker(cache=tmp_cache, cabin="business")
        cand = _make_candidate(num_segs=1)
        query = _make_query()
        checker.check_candidate(cand, query)

        # Scraper should not have been called
        mock_search.assert_not_called()
        assert cand.candidate.route_segments[0].availability.status == AvailabilityStatus.AVAILABLE


class TestErrorHandling:
    @patch("rtw.scraper.google_flights.search_fast_flights", side_effect=TimeoutError("timeout"))
    def test_timeout_marks_unknown(self, mock_search, tmp_cache):
        checker = AvailabilityChecker(cache=tmp_cache)
        cand = _make_candidate(num_segs=1)
        query = _make_query()
        checker.check_candidate(cand, query)

        assert cand.candidate.route_segments[0].availability.status == AvailabilityStatus.UNKNOWN

    @patch("rtw.scraper.google_flights.search_fast_flights", side_effect=Exception("generic error"))
    def test_exception_marks_unknown_no_crash(self, mock_search, tmp_cache):
        checker = AvailabilityChecker(cache=tmp_cache)
        cand = _make_candidate(num_segs=3)
        query = _make_query()
        # Should not crash
        checker.check_candidate(cand, query)
        for rs in cand.candidate.route_segments:
            assert rs.availability.status == AvailabilityStatus.UNKNOWN


class TestDateAssignment:
    @patch("rtw.scraper.google_flights.search_fast_flights", return_value=None)
    def test_dates_never_exceed_date_to(self, mock_search, tmp_cache):
        checker = AvailabilityChecker(cache=tmp_cache)
        cand = _make_candidate(num_segs=10)
        query = _make_query()
        dates = checker._assign_dates(cand, query)
        for d in dates:
            if d is not None:
                assert d <= query.date_to

    @patch("rtw.scraper.google_flights.search_fast_flights", return_value=None)
    def test_surface_segments_get_none_date(self, mock_search, tmp_cache):
        checker = AvailabilityChecker(cache=tmp_cache)
        cand = _make_candidate(num_segs=3, surface_indices={1})
        query = _make_query()
        dates = checker._assign_dates(cand, query)
        assert dates[1] is None
