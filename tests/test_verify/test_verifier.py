"""Tests for D-class verification orchestrator."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

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

    def test_per_carrier_booking_class_aa_uses_h(self):
        """AA segments should check H class, not D (per carriers.yaml)."""
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9, carrier="AA", origin="LAX", dest="JFK"),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("LAX", "JFK", carrier="AA"),
            ],
        )
        verifier.verify_option(option)

        # Verify the scraper was called with booking_class="H" for AA
        call_kwargs = scraper.check_availability.call_args
        assert call_kwargs.kwargs.get("booking_class") == "H" or \
               (call_kwargs.args and len(call_kwargs.args) > 4 and call_kwargs.args[4] == "H"), \
               f"Expected booking_class='H' for AA, got: {call_kwargs}"

    def test_per_carrier_booking_class_cx_uses_d(self):
        """CX segments should check D class (default from carriers.yaml)."""
        results = [
            _make_dclass(DClassStatus.AVAILABLE, 9, carrier="CX", origin="HKG", dest="SIN"),
        ]
        verifier, scraper, cache = self._make_verifier(scraper_results=results)

        option = VerifyOption(
            option_id=1,
            segments=[
                _make_segment("HKG", "SIN", carrier="CX"),
            ],
        )
        verifier.verify_option(option)

        call_kwargs = scraper.check_availability.call_args
        assert call_kwargs.kwargs.get("booking_class") == "D" or \
               (call_kwargs.args and len(call_kwargs.args) > 4 and call_kwargs.args[4] == "D"), \
               f"Expected booking_class='D' for CX, got: {call_kwargs}"

    def test_get_booking_class_method(self):
        """_get_booking_class returns correct class per carrier."""
        verifier, _, _ = self._make_verifier()
        assert verifier._get_booking_class("AA") == "H"
        assert verifier._get_booking_class("CX") == "D"
        assert verifier._get_booking_class("BA") == "D"
        assert verifier._get_booking_class("JL") == "D"
        assert verifier._get_booking_class("") == "D"
        assert verifier._get_booking_class("ZZ") == "D"  # unknown carrier
