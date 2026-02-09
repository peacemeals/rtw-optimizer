"""Tests for availability verification orchestrator."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from rtw.models import CabinClass
from rtw.scraper.expertflyer import SessionExpiredError
from rtw.verify.models import (
    DClassResult,
    DClassStatus,
    SegmentVerification,
    VerifyOption,
)
from rtw.verify.verifier import DClassVerifier


def _make_segment(origin, dest, carrier="CX", stype="FLOWN", date=None):
    return SegmentVerification(
        index=0,
        segment_type=stype,
        origin=origin,
        destination=dest,
        carrier=carrier,
        target_date=date or datetime.date(2026, 3, 10),
    )


def _make_dclass(status, seats, carrier="CX", origin="LHR", dest="HKG"):
    return DClassResult(
        status=status,
        seats=seats,
        carrier=carrier,
        origin=origin,
        destination=dest,
        target_date=datetime.date(2026, 3, 10),
    )


class TestDClassVerifier:
    def _make_verifier(self, scraper_results=None, cache_results=None):
        """Create a verifier with mocked scraper and cache."""
        scraper = MagicMock()
        if scraper_results is not None:
            scraper.check_availability.side_effect = scraper_results
        cache = MagicMock()
        cache.get.return_value = cache_results
        return DClassVerifier(scraper=scraper, cache=cache), scraper, cache

    def test_all_available(self):
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9, origin="SYD", dest="HKG"),
            _make_dclass(DClassStatus.AVAILABLE, 5, origin="HKG", dest="LHR"),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("SYD", "HKG"),
                _make_segment("HKG", "LHR"),
            ],
        )
        result = verifier.verify_option(option)
        assert result.confirmed == 2
        assert result.total_flown == 2
        assert result.fully_bookable is True
        assert scraper.check_availability.call_count == 2

    def test_surface_skipped(self):
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("SYD", "HKG"),
                _make_segment("HKG", "LHR", stype="SURFACE"),
            ],
        )
        result = verifier.verify_option(option)
        assert result.confirmed == 1
        assert result.total_flown == 1
        assert result.fully_bookable is True
        # Scraper only called once (surface skipped)
        assert scraper.check_availability.call_count == 1

    def test_partial_failure(self):
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9),
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("SYD", "HKG"),
                _make_segment("HKG", "LHR"),
            ],
        )
        result = verifier.verify_option(option)
        assert result.confirmed == 1
        assert result.total_flown == 2
        assert result.fully_bookable is False

    def test_session_expired_marks_remaining_unknown(self):
        verifier, scraper, cache = self._make_verifier()
        scraper.check_availability.side_effect = [
            _make_dclass(DClassStatus.AVAILABLE, 9),
            SessionExpiredError("expired"),
        ]

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("SYD", "HKG"),
                _make_segment("HKG", "LHR"),
                _make_segment("LHR", "JFK"),
            ],
        )
        result = verifier.verify_option(option)
        statuses = [s.dclass.status for s in result.segments if s.dclass]
        assert statuses[0] == DClassStatus.AVAILABLE
        assert statuses[1] == DClassStatus.UNKNOWN
        assert statuses[2] == DClassStatus.UNKNOWN

    def test_scrape_error_marks_error(self):
        verifier, scraper, cache = self._make_verifier()
        scraper.check_availability.side_effect = [
            _make_dclass(DClassStatus.AVAILABLE, 9),
            Exception("timeout"),
            _make_dclass(DClassStatus.AVAILABLE, 5),
        ]

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("SYD", "HKG"),
                _make_segment("HKG", "LHR"),
                _make_segment("LHR", "JFK"),
            ],
        )
        result = verifier.verify_option(option)
        statuses = [s.dclass.status for s in result.segments if s.dclass]
        assert statuses[0] == DClassStatus.AVAILABLE
        assert statuses[1] == DClassStatus.ERROR
        assert statuses[2] == DClassStatus.AVAILABLE

    def test_progress_callback(self):
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9),
            _make_dclass(DClassStatus.AVAILABLE, 5),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        progress_calls = []

        def cb(current, total, seg):
            progress_calls.append((current, total))

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("SYD", "HKG"),
                _make_segment("HKG", "LHR"),
            ],
        )
        verifier.verify_option(option, progress_cb=cb)
        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2)
        assert progress_calls[1] == (2, 2)

    def test_batch_verify(self):
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9),
            _make_dclass(DClassStatus.AVAILABLE, 5),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        options = [
            VerifyOption(option_id=1, segments=[_make_segment("SYD", "HKG")]),
            VerifyOption(option_id=2, segments=[_make_segment("HKG", "LHR")]),
        ]
        results = verifier.verify_batch(options)
        assert len(results) == 2
        assert results[0].option_id == 1
        assert results[1].option_id == 2

    def test_empty_option(self):
        verifier, scraper, cache = self._make_verifier()
        option = VerifyOption(option_id=1, segments=[])
        result = verifier.verify_option(option)
        assert result.total_flown == 0
        assert result.fully_bookable is True
        assert scraper.check_availability.call_count == 0

    def test_aa_segment_uses_h_class(self):
        """AA segments should be queried with booking_class='H'."""
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9, carrier="AA", origin="JFK", dest="LAX"),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[_make_segment("JFK", "LAX", carrier="AA")],
        )
        verifier.verify_option(option)
        call_kwargs = scraper.check_availability.call_args[1]
        assert call_kwargs["booking_class"] == "H"

    def test_cx_segment_uses_d_class(self):
        """Non-AA carriers should use D class."""
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[_make_segment("SYD", "HKG", carrier="CX")],
        )
        verifier.verify_option(option)
        call_kwargs = scraper.check_availability.call_args[1]
        assert call_kwargs["booking_class"] == "D"

    def test_mixed_carriers_use_correct_classes(self):
        """AA gets H, CX gets D, BA gets D in the same option."""
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9, carrier="AA", origin="JFK", dest="LHR"),
            _make_dclass(DClassStatus.AVAILABLE, 5, carrier="CX", origin="LHR", dest="HKG"),
            _make_dclass(DClassStatus.AVAILABLE, 7, carrier="BA", origin="HKG", dest="SYD"),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("JFK", "LHR", carrier="AA"),
                _make_segment("LHR", "HKG", carrier="CX"),
                _make_segment("HKG", "SYD", carrier="BA"),
            ],
        )
        verifier.verify_option(option)
        calls = scraper.check_availability.call_args_list
        assert calls[0][1]["booking_class"] == "H"  # AA
        assert calls[1][1]["booking_class"] == "D"  # CX
        assert calls[2][1]["booking_class"] == "D"  # BA

    def test_booking_class_override_forces_all(self):
        """Explicit booking_class override forces all segments to that class."""
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9, carrier="AA", origin="JFK", dest="LHR"),
            _make_dclass(DClassStatus.AVAILABLE, 5, carrier="CX", origin="LHR", dest="HKG"),
        ]
        scraper = MagicMock()
        scraper.check_availability.side_effect = results
        cache = MagicMock()
        cache.get.return_value = None
        verifier = DClassVerifier(scraper=scraper, cache=cache, booking_class="D")

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("JFK", "LHR", carrier="AA"),
                _make_segment("LHR", "HKG", carrier="CX"),
            ],
        )
        verifier.verify_option(option)
        calls = scraper.check_availability.call_args_list
        assert calls[0][1]["booking_class"] == "D"  # Override: AA forced to D
        assert calls[1][1]["booking_class"] == "D"  # CX stays D

    def test_cache_key_includes_correct_booking_class(self):
        """AA cache key should contain H, CX cache key should contain D."""
        verifier, scraper, cache = self._make_verifier()

        aa_seg = _make_segment("JFK", "LHR", carrier="AA")
        cx_seg = _make_segment("LHR", "HKG", carrier="CX")

        aa_key = verifier._cache_key(aa_seg)
        cx_key = verifier._cache_key(cx_seg)

        assert "_H" in aa_key
        assert "_D" in cx_key

    def test_dclass_result_has_booking_class_set(self):
        """DClassResult returned for AA should have booking_class='H'."""
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9, carrier="AA", origin="JFK", dest="LHR"),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[_make_segment("JFK", "LHR", carrier="AA")],
        )
        result = verifier.verify_option(option)
        assert result.segments[0].dclass.booking_class == "H"


class TestDateFlex:
    """Tests for the ±3 days date flex feature."""

    def _make_verifier(self, scraper_results=None, date_flex=True):
        scraper = MagicMock()
        if scraper_results is not None:
            scraper.check_availability.side_effect = scraper_results
        cache = MagicMock()
        cache.get.return_value = None
        return DClassVerifier(scraper=scraper, cache=cache, date_flex=date_flex), scraper, cache

    def test_date_flex_not_triggered_when_available(self):
        """If target date has availability, no alternate dates are checked."""
        target_result = _make_dclass(DClassStatus.AVAILABLE, 5, origin="SYD", dest="HKG")
        verifier, scraper, cache = self._make_verifier(scraper_results=[target_result])

        option = VerifyOption(
            option_id=1,
            segments=[_make_segment("SYD", "HKG", date=datetime.date(2026, 4, 6))],
        )
        result = verifier.verify_option(option)
        # Only 1 call: the target date. No alternate date queries.
        assert scraper.check_availability.call_count == 1
        assert result.segments[0].dclass.seats == 5
        assert result.segments[0].dclass.alternate_dates == []

    def test_date_flex_checks_alternates_when_sold_out(self):
        """If target date is D0, ±3 days are checked."""
        target_result = _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="SYD", dest="HKG")
        # Alternates: +1=D0, -1=D3, +2=D5, -2=D0, +3=D0, -3=D0
        alt_results = [
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="SYD", dest="HKG"),  # +1
            _make_dclass(DClassStatus.AVAILABLE, 3, origin="SYD", dest="HKG"),  # -1
            _make_dclass(DClassStatus.AVAILABLE, 5, origin="SYD", dest="HKG"),  # +2
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="SYD", dest="HKG"),  # -2
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="SYD", dest="HKG"),  # +3
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="SYD", dest="HKG"),  # -3
        ]
        verifier, scraper, cache = self._make_verifier(
            scraper_results=[target_result] + alt_results,
        )

        option = VerifyOption(
            option_id=1,
            segments=[_make_segment("SYD", "HKG", date=datetime.date(2026, 4, 6))],
        )
        result = verifier.verify_option(option)
        # 1 target + 6 alternates = 7 calls
        assert scraper.check_availability.call_count == 7
        seg = result.segments[0]
        assert seg.dclass.seats == 0
        assert len(seg.dclass.alternate_dates) == 2  # -1 (D3) and +2 (D5)

        # Best alternate should be +2 (D5)
        best = seg.dclass.best_alternate
        assert best is not None
        assert best.seats == 5
        assert best.offset_days == 2
        assert best.date == datetime.date(2026, 4, 8)

    def test_date_flex_disabled_by_default(self):
        """With date_flex=False, no alternate dates are checked."""
        target_result = _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="SYD", dest="HKG")
        verifier, scraper, cache = self._make_verifier(
            scraper_results=[target_result],
            date_flex=False,
        )

        option = VerifyOption(
            option_id=1,
            segments=[_make_segment("SYD", "HKG", date=datetime.date(2026, 4, 6))],
        )
        result = verifier.verify_option(option)
        assert scraper.check_availability.call_count == 1
        assert result.segments[0].dclass.alternate_dates == []

    def test_date_flex_stops_on_session_expired(self):
        """If session expires during flex checks, remaining are skipped."""
        target_result = _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="SYD", dest="HKG")
        verifier, scraper, cache = self._make_verifier(
            scraper_results=[
                target_result,
                _make_dclass(DClassStatus.AVAILABLE, 3, origin="SYD", dest="HKG"),  # +1
                SessionExpiredError("expired"),  # -1 fails
            ],
        )

        option = VerifyOption(
            option_id=1,
            segments=[_make_segment("SYD", "HKG", date=datetime.date(2026, 4, 6))],
        )
        result = verifier.verify_option(option)
        seg = result.segments[0]
        # Should have 1 alternate (from +1 day before session expired)
        assert len(seg.dclass.alternate_dates) == 1
        assert seg.dclass.alternate_dates[0].offset_days == 1

    def test_date_flex_with_multiple_segments(self):
        """Date flex only applies to sold-out segments."""
        # Seg 1: D9 (no flex needed), Seg 2: D0 (flex), plus alternates for seg 2
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9, origin="SYD", dest="HKG"),  # seg 1
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="HKG", dest="LHR"),  # seg 2
            # Flex queries for seg 2:
            _make_dclass(DClassStatus.AVAILABLE, 2, origin="HKG", dest="LHR"),  # +1
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="HKG", dest="LHR"),  # -1
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="HKG", dest="LHR"),  # +2
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="HKG", dest="LHR"),  # -2
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="HKG", dest="LHR"),  # +3
            _make_dclass(DClassStatus.NOT_AVAILABLE, 0, origin="HKG", dest="LHR"),  # -3
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("SYD", "HKG", date=datetime.date(2026, 4, 6)),
                _make_segment("HKG", "LHR", date=datetime.date(2026, 4, 10)),
            ],
        )
        result = verifier.verify_option(option)
        # Seg 1: 1 call (available, no flex)
        # Seg 2: 1 target + 6 alternates = 7 calls
        assert scraper.check_availability.call_count == 8
        assert result.segments[0].dclass.alternate_dates == []
        assert len(result.segments[1].dclass.alternate_dates) == 1
        assert result.segments[1].dclass.alternate_dates[0].offset_days == 1
