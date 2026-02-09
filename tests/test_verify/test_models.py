"""Tests for D-class verification models."""

import datetime

import pytest

from rtw.verify.models import (
    AlternateDateResult,
    DClassResult,
    DClassStatus,
    FlightAvailability,
    SegmentVerification,
    VerifyOption,
    VerifyResult,
)


class TestDClassStatus:
    def test_all_statuses(self):
        assert set(DClassStatus) == {
            DClassStatus.AVAILABLE,
            DClassStatus.NOT_AVAILABLE,
            DClassStatus.UNKNOWN,
            DClassStatus.ERROR,
            DClassStatus.CACHED,
        }


class TestDClassResult:
    def test_available(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE,
            seats=5,
            carrier="CX",
            origin="LHR",
            destination="HKG",
            target_date=datetime.date(2026, 3, 10),
        )
        assert r.available is True
        assert r.display_code == "D5"
        assert r.seats == 5

    def test_not_available(self):
        r = DClassResult(
            status=DClassStatus.NOT_AVAILABLE,
            seats=0,
            carrier="CX",
            origin="LHR",
            destination="HKG",
            target_date=datetime.date(2026, 3, 10),
        )
        assert r.available is False
        assert r.display_code == "D0"

    def test_unknown(self):
        r = DClassResult(
            status=DClassStatus.UNKNOWN,
            seats=0,
            carrier="CX",
            origin="LHR",
            destination="HKG",
            target_date=datetime.date(2026, 3, 10),
        )
        assert r.available is False
        assert r.display_code == "D?"

    def test_error(self):
        r = DClassResult(
            status=DClassStatus.ERROR,
            seats=0,
            carrier="CX",
            origin="LHR",
            destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            error_message="timeout",
        )
        assert r.available is False
        assert r.display_code == "D!"

    def test_serialization_roundtrip(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE,
            seats=9,
            carrier="CX",
            origin="LHR",
            destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            flight_number="CX252",
            from_cache=True,
            alternate_dates=[
                AlternateDateResult(
                    date=datetime.date(2026, 3, 11), seats=7, offset_days=1
                ),
            ],
        )
        data = r.model_dump(mode="json")
        r2 = DClassResult.model_validate(data)
        assert r2.status == DClassStatus.AVAILABLE
        assert r2.seats == 9
        assert r2.carrier == "CX"
        assert r2.flight_number == "CX252"
        assert r2.from_cache is True
        assert len(r2.alternate_dates) == 1
        assert r2.alternate_dates[0].seats == 7

    def test_best_alternate_none(self):
        r = DClassResult(
            status=DClassStatus.NOT_AVAILABLE,
            seats=0,
            carrier="CX",
            origin="LHR",
            destination="HKG",
            target_date=datetime.date(2026, 3, 10),
        )
        assert r.best_alternate is None

    def test_best_alternate(self):
        r = DClassResult(
            status=DClassStatus.NOT_AVAILABLE,
            seats=0,
            carrier="CX",
            origin="LHR",
            destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            alternate_dates=[
                AlternateDateResult(
                    date=datetime.date(2026, 3, 8), seats=0, offset_days=-2
                ),
                AlternateDateResult(
                    date=datetime.date(2026, 3, 11), seats=3, offset_days=1
                ),
                AlternateDateResult(
                    date=datetime.date(2026, 3, 12), seats=9, offset_days=2
                ),
            ],
        )
        best = r.best_alternate
        assert best is not None
        assert best.seats == 9
        assert best.offset_days == 2


class TestAlternateDateResult:
    def test_valid(self):
        a = AlternateDateResult(
            date=datetime.date(2026, 3, 11), seats=5, offset_days=1
        )
        assert a.seats == 5
        assert a.offset_days == 1

    def test_seats_bounds(self):
        with pytest.raises(Exception):
            AlternateDateResult(
                date=datetime.date(2026, 3, 11), seats=10, offset_days=1
            )


class TestVerifyResult:
    def _make_result(self, statuses):
        """Helper: build VerifyResult with given D-class statuses."""
        segments = []
        for i, (stype, status, seats) in enumerate(statuses):
            dclass = None
            if status is not None:
                dclass = DClassResult(
                    status=status,
                    seats=seats,
                    carrier="CX",
                    origin="LHR",
                    destination="HKG",
                    target_date=datetime.date(2026, 3, 10),
                )
            segments.append(
                SegmentVerification(
                    index=i,
                    segment_type=stype,
                    origin="LHR",
                    destination="HKG",
                    carrier="CX",
                    dclass=dclass,
                )
            )
        return VerifyResult(option_id=1, segments=segments)

    def test_all_available(self):
        r = self._make_result([
            ("FLOWN", DClassStatus.AVAILABLE, 9),
            ("FLOWN", DClassStatus.AVAILABLE, 5),
            ("FLOWN", DClassStatus.AVAILABLE, 3),
        ])
        assert r.confirmed == 3
        assert r.total_flown == 3
        assert r.percentage == 100.0
        assert r.fully_bookable is True

    def test_partial_available(self):
        r = self._make_result([
            ("FLOWN", DClassStatus.AVAILABLE, 9),
            ("FLOWN", DClassStatus.NOT_AVAILABLE, 0),
            ("FLOWN", DClassStatus.AVAILABLE, 3),
        ])
        assert r.confirmed == 2
        assert r.total_flown == 3
        assert r.percentage == pytest.approx(66.67, abs=0.1)
        assert r.fully_bookable is False

    def test_surface_segments_excluded(self):
        r = self._make_result([
            ("FLOWN", DClassStatus.AVAILABLE, 9),
            ("SURFACE", None, 0),
            ("FLOWN", DClassStatus.AVAILABLE, 5),
        ])
        assert r.confirmed == 2
        assert r.total_flown == 2
        assert r.percentage == 100.0
        assert r.fully_bookable is True

    def test_empty_vacuously_true(self):
        r = VerifyResult(option_id=1, segments=[])
        assert r.confirmed == 0
        assert r.total_flown == 0
        assert r.percentage == 0.0
        assert r.fully_bookable is True

    def test_all_surface_vacuously_true(self):
        r = self._make_result([
            ("SURFACE", None, 0),
            ("SURFACE", None, 0),
        ])
        assert r.total_flown == 0
        assert r.fully_bookable is True


class TestFlightAvailability:
    def test_basic_creation(self):
        f = FlightAvailability(
            carrier="CX",
            flight_number="CX252",
            origin="LHR",
            destination="HKG",
            depart_time="03/10/26 11:00 AM",
            arrive_time="03/11/26 7:00 AM",
            aircraft="77W",
            seats=9,
            booking_class="D",
            stops=0,
        )
        assert f.carrier == "CX"
        assert f.flight_number == "CX252"
        assert f.seats == 9
        assert f.stops == 0

    def test_defaults(self):
        f = FlightAvailability()
        assert f.carrier is None
        assert f.flight_number is None
        assert f.seats == 0
        assert f.booking_class == "D"
        assert f.stops == 0

    def test_seats_bounds(self):
        with pytest.raises(Exception):
            FlightAvailability(seats=10)
        with pytest.raises(Exception):
            FlightAvailability(seats=-1)

    def test_serialization_roundtrip(self):
        f = FlightAvailability(
            carrier="QF", flight_number="QF11", seats=6, aircraft="388",
        )
        data = f.model_dump(mode="json")
        f2 = FlightAvailability.model_validate(data)
        assert f2.carrier == "QF"
        assert f2.flight_number == "QF11"
        assert f2.seats == 6


class TestDClassResultWithFlights:
    def _make_flights(self):
        return [
            FlightAvailability(carrier="CX", flight_number="CX252", seats=9,
                               depart_time="03/10/26 11:00 AM"),
            FlightAvailability(carrier="CX", flight_number="CX254", seats=6,
                               depart_time="03/10/26 10:05 PM"),
            FlightAvailability(carrier="CX", flight_number="CX256", seats=0,
                               depart_time="03/10/26 8:15 PM"),
            FlightAvailability(carrier="BA", flight_number="BA708", seats=9,
                               depart_time="03/10/26 6:30 AM"),
        ]

    def test_flight_count(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            flights=self._make_flights(),
        )
        assert r.flight_count == 4

    def test_available_count(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            flights=self._make_flights(),
        )
        assert r.available_count == 3  # CX252(9), CX254(6), BA708(9)

    def test_available_flights_sorted(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            flights=self._make_flights(),
        )
        avail = r.available_flights
        assert len(avail) == 3
        # Sorted by seats desc, then departure time string asc
        assert avail[0].seats == 9
        assert avail[1].seats == 9
        assert avail[2].seats == 6
        assert avail[2].flight_number == "CX254"  # D6 last
        # D0 flight (CX256) should be excluded
        assert all(f.seats > 0 for f in avail)

    def test_display_code_with_flights(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            flights=self._make_flights(),
        )
        assert r.display_code == "D9 (3 avl)"

    def test_display_code_no_flights(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
        )
        assert r.display_code == "D9"

    def test_display_code_all_d0(self):
        flights = [
            FlightAvailability(carrier="CX", flight_number="CX252", seats=0),
            FlightAvailability(carrier="CX", flight_number="CX254", seats=0),
        ]
        r = DClassResult(
            status=DClassStatus.NOT_AVAILABLE, seats=0, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            flights=flights,
        )
        assert r.display_code == "D0 (0 avl)"

    def test_serialization_with_flights(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            flights=self._make_flights(),
        )
        data = r.model_dump(mode="json")
        r2 = DClassResult.model_validate(data)
        assert r2.flight_count == 4
        assert r2.available_count == 3
        assert r2.flights[0].flight_number == "CX252"


class TestBookingClassDisplay:
    """Test display_code with different booking classes."""

    def test_h_class_available(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="AA",
            origin="JFK", destination="LHR",
            target_date=datetime.date(2026, 3, 10),
            booking_class="H",
        )
        assert r.display_code == "H9"

    def test_h_class_not_available(self):
        r = DClassResult(
            status=DClassStatus.NOT_AVAILABLE, seats=0, carrier="AA",
            origin="JFK", destination="LHR",
            target_date=datetime.date(2026, 3, 10),
            booking_class="H",
        )
        assert r.display_code == "H0"

    def test_h_class_unknown(self):
        r = DClassResult(
            status=DClassStatus.UNKNOWN, seats=0, carrier="AA",
            origin="JFK", destination="LHR",
            target_date=datetime.date(2026, 3, 10),
            booking_class="H",
        )
        assert r.display_code == "H?"

    def test_h_class_error(self):
        r = DClassResult(
            status=DClassStatus.ERROR, seats=0, carrier="AA",
            origin="JFK", destination="LHR",
            target_date=datetime.date(2026, 3, 10),
            booking_class="H",
            error_message="timeout",
        )
        assert r.display_code == "H!"

    def test_h_class_with_flights(self):
        flights = [
            FlightAvailability(carrier="AA", flight_number="AA100", seats=9, booking_class="H"),
            FlightAvailability(carrier="AA", flight_number="AA106", seats=0, booking_class="H"),
        ]
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="AA",
            origin="JFK", destination="LHR",
            target_date=datetime.date(2026, 3, 10),
            booking_class="H",
            flights=flights,
        )
        assert r.display_code == "H9 (1 avl)"

    def test_default_booking_class_is_d(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=5, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
        )
        assert r.booking_class == "D"
        assert r.display_code == "D5"

    def test_booking_class_serialization_roundtrip(self):
        r = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="AA",
            origin="JFK", destination="LHR",
            target_date=datetime.date(2026, 3, 10),
            booking_class="H",
        )
        data = r.model_dump(mode="json")
        r2 = DClassResult.model_validate(data)
        assert r2.booking_class == "H"
        assert r2.display_code == "H9"

    def test_flight_availability_h_class(self):
        f = FlightAvailability(
            carrier="AA", flight_number="AA100", seats=9, booking_class="H",
        )
        assert f.booking_class == "H"
