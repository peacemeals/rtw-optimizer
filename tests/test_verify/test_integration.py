"""Integration test for the full D-class verify pipeline.

Tests: SearchResult → save to state → load → convert to VerifyOption
→ run DClassVerifier with mocked scraper → check VerifyResult.
"""

import datetime
from io import StringIO
from unittest.mock import MagicMock

import pytest

from rtw.models import CabinClass, Itinerary, Ticket, TicketType
from rtw.scraper.expertflyer import SessionExpiredError
from rtw.search.models import (
    CandidateItinerary,
    Direction,
    ScoredCandidate,
    SearchQuery,
    SearchResult,
)
from rtw.verify.models import DClassResult, DClassStatus, SegmentVerification, VerifyOption
from rtw.verify.state import SearchState
from rtw.verify.verifier import DClassVerifier


def _build_search_result():
    """Build a realistic 4-segment SearchResult."""
    query = SearchQuery(
        cities=["SYD", "HKG", "LHR", "JFK"],
        origin="SYD",
        date_from=datetime.date(2026, 9, 1),
        date_to=datetime.date(2026, 10, 15),
        cabin=CabinClass.BUSINESS,
        ticket_type=TicketType.DONE4,
    )
    ticket = Ticket(type=TicketType.DONE4, cabin=CabinClass.BUSINESS, origin="SYD")
    itin = Itinerary(
        ticket=ticket,
        segments=[
            {"from": "SYD", "to": "HKG", "carrier": "CX", "type": "stopover",
             "date": "2026-09-01"},
            {"from": "HKG", "to": "LHR", "carrier": "CX", "type": "stopover",
             "date": "2026-09-05"},
            {"from": "LHR", "to": "JFK", "carrier": "BA", "type": "stopover",
             "date": "2026-09-12"},
            {"from": "JFK", "to": "SYD", "carrier": "QF", "type": "final",
             "date": "2026-09-20"},
        ],
    )
    candidate = CandidateItinerary(itinerary=itin, direction=Direction.EASTBOUND)
    scored = ScoredCandidate(candidate=candidate, composite_score=85.0, rank=1)

    return SearchResult(
        query=query,
        candidates_generated=10,
        options=[scored],
        base_fare_usd=6299.0,
    )


class TestFullPipeline:
    """End-to-end: save → load → convert → verify → result."""

    def test_save_load_convert_verify(self, tmp_path):
        """Full pipeline with all segments available."""
        # Step 1: Save search result
        state = SearchState(state_path=tmp_path / "state.json")
        sr = _build_search_result()
        state.save(sr)

        # Step 2: Load it back
        loaded = state.load()
        assert loaded is not None
        assert len(loaded.options) == 1

        # Step 3: Convert to VerifyOption
        from rtw.cli import _scored_to_verify_option

        option = _scored_to_verify_option(loaded.options[0], 1)
        assert option.option_id == 1
        assert len(option.segments) == 4
        assert all(s.segment_type == "FLOWN" for s in option.segments)
        assert option.segments[0].origin == "SYD"
        assert option.segments[0].carrier == "CX"
        assert option.segments[0].target_date == datetime.date(2026, 9, 1)

        # Step 4: Verify with mocked scraper
        def _make_result(seg):
            return DClassResult(
                status=DClassStatus.AVAILABLE,
                seats=9,
                carrier=seg.carrier or "??",
                origin=seg.origin,
                destination=seg.destination,
                target_date=seg.target_date or datetime.date(2026, 9, 1),
            )

        scraper = MagicMock()
        scraper.check_availability.side_effect = [
            _make_result(option.segments[0]),
            _make_result(option.segments[1]),
            _make_result(option.segments[2]),
            _make_result(option.segments[3]),
        ]
        cache = MagicMock()
        cache.get.return_value = None

        verifier = DClassVerifier(scraper=scraper, cache=cache)
        result = verifier.verify_option(option)

        # Step 5: Check result
        assert result.option_id == 1
        assert result.total_flown == 4
        assert result.confirmed == 4
        assert result.fully_bookable is True
        assert result.percentage == 100.0
        assert scraper.check_availability.call_count == 4

    def test_pipeline_with_surface_segment(self, tmp_path):
        """Pipeline with a surface segment that gets skipped."""
        query = SearchQuery(
            cities=["SYD", "HKG", "BKK", "LHR"],
            origin="SYD",
            date_from=datetime.date(2026, 9, 1),
            date_to=datetime.date(2026, 10, 15),
            cabin=CabinClass.BUSINESS,
            ticket_type=TicketType.DONE4,
        )
        ticket = Ticket(type=TicketType.DONE4, cabin=CabinClass.BUSINESS, origin="SYD")
        itin = Itinerary(
            ticket=ticket,
            segments=[
                {"from": "SYD", "to": "HKG", "carrier": "CX", "type": "stopover"},
                {"from": "HKG", "to": "BKK", "type": "surface"},
                {"from": "BKK", "to": "LHR", "carrier": "BA", "type": "stopover"},
                {"from": "LHR", "to": "SYD", "carrier": "QF", "type": "final"},
            ],
        )
        candidate = CandidateItinerary(itinerary=itin, direction=Direction.EASTBOUND)
        scored = ScoredCandidate(candidate=candidate, rank=1)
        sr = SearchResult(
            query=query, candidates_generated=5, options=[scored], base_fare_usd=6299.0,
        )

        state = SearchState(state_path=tmp_path / "state.json")
        state.save(sr)
        loaded = state.load()

        from rtw.cli import _scored_to_verify_option

        option = _scored_to_verify_option(loaded.options[0], 1)
        assert option.segments[1].segment_type == "SURFACE"

        # Only 3 scraper calls (surface skipped)
        scraper = MagicMock()
        scraper.check_availability.side_effect = [
            DClassResult(
                status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
                origin="SYD", destination="HKG",
                target_date=datetime.date(2026, 9, 1),
            ),
            DClassResult(
                status=DClassStatus.NOT_AVAILABLE, seats=0, carrier="BA",
                origin="BKK", destination="LHR",
                target_date=datetime.date(2026, 9, 1),
            ),
            DClassResult(
                status=DClassStatus.AVAILABLE, seats=5, carrier="QF",
                origin="LHR", destination="SYD",
                target_date=datetime.date(2026, 9, 1),
            ),
        ]
        cache = MagicMock()
        cache.get.return_value = None

        verifier = DClassVerifier(scraper=scraper, cache=cache)
        result = verifier.verify_option(option)

        assert result.total_flown == 3  # Surface excluded
        assert result.confirmed == 2  # BKK-LHR not available
        assert result.fully_bookable is False
        assert scraper.check_availability.call_count == 3

    def test_pipeline_session_expired_midway(self, tmp_path):
        """Session expires after first segment — remaining marked UNKNOWN."""
        state = SearchState(state_path=tmp_path / "state.json")
        sr = _build_search_result()
        state.save(sr)
        loaded = state.load()

        from rtw.cli import _scored_to_verify_option

        option = _scored_to_verify_option(loaded.options[0], 1)

        scraper = MagicMock()
        scraper.check_availability.side_effect = [
            DClassResult(
                status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
                origin="SYD", destination="HKG",
                target_date=datetime.date(2026, 9, 1),
            ),
            SessionExpiredError("session expired"),
        ]
        cache = MagicMock()
        cache.get.return_value = None

        verifier = DClassVerifier(scraper=scraper, cache=cache)
        result = verifier.verify_option(option)

        statuses = [s.dclass.status for s in result.segments if s.dclass]
        assert statuses[0] == DClassStatus.AVAILABLE
        assert statuses[1] == DClassStatus.UNKNOWN
        assert statuses[2] == DClassStatus.UNKNOWN
        assert statuses[3] == DClassStatus.UNKNOWN
        assert result.confirmed == 1
        assert result.fully_bookable is False

    def test_display_does_not_crash(self, tmp_path):
        """_display_verify_result doesn't crash with various result shapes."""
        from rtw.cli import _display_verify_result
        from rtw.verify.models import VerifyResult

        # Empty result
        empty = VerifyResult(option_id=1, segments=[])
        _display_verify_result(empty)  # Should not raise

        # Result with all statuses
        segments = [
            SegmentVerification(
                index=0, segment_type="FLOWN", origin="SYD", destination="HKG",
                carrier="CX", target_date=datetime.date(2026, 9, 1),
                dclass=DClassResult(
                    status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
                    origin="SYD", destination="HKG",
                    target_date=datetime.date(2026, 9, 1),
                ),
            ),
            SegmentVerification(
                index=1, segment_type="SURFACE", origin="HKG", destination="BKK",
            ),
            SegmentVerification(
                index=2, segment_type="FLOWN", origin="BKK", destination="LHR",
                carrier="BA", target_date=datetime.date(2026, 9, 5),
                dclass=DClassResult(
                    status=DClassStatus.NOT_AVAILABLE, seats=0, carrier="BA",
                    origin="BKK", destination="LHR",
                    target_date=datetime.date(2026, 9, 5),
                ),
            ),
            SegmentVerification(
                index=3, segment_type="FLOWN", origin="LHR", destination="SYD",
                carrier="QF", target_date=datetime.date(2026, 9, 12),
                dclass=DClassResult(
                    status=DClassStatus.ERROR, seats=0, carrier="QF",
                    origin="LHR", destination="SYD",
                    target_date=datetime.date(2026, 9, 12),
                    error_message="timeout",
                ),
            ),
            SegmentVerification(
                index=4, segment_type="FLOWN", origin="SYD", destination="SYD",
                carrier="QF",
                dclass=None,  # Not checked
            ),
        ]
        mixed = VerifyResult(option_id=2, segments=segments)
        _display_verify_result(mixed)  # Should not raise

    def test_summary_does_not_crash(self):
        """_display_verify_summary doesn't crash."""
        from rtw.cli import _display_verify_summary
        from rtw.verify.models import VerifyResult

        results = [
            VerifyResult(option_id=1, segments=[
                SegmentVerification(
                    index=0, segment_type="FLOWN", origin="SYD", destination="HKG",
                    dclass=DClassResult(
                        status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
                        origin="SYD", destination="HKG",
                        target_date=datetime.date(2026, 9, 1),
                    ),
                ),
            ]),
            VerifyResult(option_id=2, segments=[
                SegmentVerification(
                    index=0, segment_type="FLOWN", origin="SYD", destination="LHR",
                    dclass=DClassResult(
                        status=DClassStatus.NOT_AVAILABLE, seats=0, carrier="BA",
                        origin="SYD", destination="LHR",
                        target_date=datetime.date(2026, 9, 1),
                    ),
                ),
            ]),
        ]
        _display_verify_summary(results)  # Should not raise
