"""Tests for rtw.ntp NTP calculator."""

import pytest

from rtw.models import Itinerary, NTPMethod
from rtw.ntp import NTPCalculator


@pytest.fixture
def calc():
    return NTPCalculator()


def _make_itinerary(segments, origin="CAI", ticket_type="DONE4"):
    """Build a minimal Itinerary for testing."""
    return Itinerary.model_validate(
        {
            "ticket": {"type": ticket_type, "cabin": "business", "origin": origin},
            "segments": segments,
        }
    )


# ------------------------------------------------------------------
# Distance-based NTP tests
# ------------------------------------------------------------------


class TestDistanceBased:
    """Distance-based NTP earning: NTP = distance * (rate / 100)."""

    def test_qr_doh_nrt_d_class(self, calc):
        """QR DOH-NRT in D class: 50% of ~5156 miles = ~2578 NTP."""
        itin = _make_itinerary(
            [
                {"from": "DOH", "to": "NRT", "carrier": "QR"},
            ]
        )
        results = calc.calculate(itin, booking_class="D")
        assert len(results) == 1
        est = results[0]
        assert est.method == NTPMethod.DISTANCE
        assert est.rate == 50
        assert est.confidence == "calculated"
        assert est.estimated_ntp == pytest.approx(2578, abs=25)

    def test_cx_tpe_hkg_d_class(self, calc):
        """CX TPE-HKG in D class: 25% of ~501 miles = ~125 NTP."""
        itin = _make_itinerary(
            [
                {"from": "TPE", "to": "HKG", "carrier": "CX"},
            ]
        )
        results = calc.calculate(itin, booking_class="D")
        est = results[0]
        assert est.method == NTPMethod.DISTANCE
        assert est.rate == 25
        assert est.estimated_ntp == pytest.approx(125, abs=25)

    def test_fj_nan_sfo_d_class(self, calc):
        """FJ NAN-SFO in D class: 25% of ~5466 miles = ~1366 NTP."""
        itin = _make_itinerary(
            [
                {"from": "NAN", "to": "SFO", "carrier": "FJ"},
            ]
        )
        results = calc.calculate(itin, booking_class="D")
        est = results[0]
        assert est.method == NTPMethod.DISTANCE
        assert est.rate == 25
        assert est.estimated_ntp == pytest.approx(1366, abs=25)

    def test_rj_cai_amm_d_class(self, calc):
        """RJ CAI-AMM in D class: 25% of ~294 miles = ~73 NTP."""
        itin = _make_itinerary(
            [
                {"from": "CAI", "to": "AMM", "carrier": "RJ"},
            ]
        )
        results = calc.calculate(itin, booking_class="D")
        est = results[0]
        assert est.method == NTPMethod.DISTANCE
        assert est.rate == 25
        assert est.estimated_ntp == pytest.approx(73, abs=25)

    def test_fj_atr72_earns_at_d_rate(self, calc):
        """FJ ATR-72 segment (NAN-FUN, short-haul): D maps to Y but earns at D rate."""
        itin = _make_itinerary(
            [
                {"from": "NAN", "to": "FUN", "carrier": "FJ"},
            ]
        )
        results = calc.calculate(itin, booking_class="D")
        est = results[0]
        assert est.rate == 25  # D-class rate, not Y-class
        assert est.estimated_ntp == pytest.approx(162, abs=25)
        assert "ATR-72" in est.notes


# ------------------------------------------------------------------
# Revenue-based NTP tests
# ------------------------------------------------------------------


class TestRevenueBased:
    """Revenue-based NTP earning: 1 NTP per GBP 1 of eligible spend."""

    def test_aa_segment_is_revenue_based(self, calc):
        """AA segments should use revenue method with estimated confidence."""
        itin = _make_itinerary(
            [
                {"from": "SFO", "to": "JFK", "carrier": "AA"},
            ]
        )
        results = calc.calculate(itin, booking_class="D", total_fare_usd=4000)
        est = results[0]
        assert est.method == NTPMethod.REVENUE
        assert est.confidence == "estimated"
        assert est.estimated_ntp > 0

    def test_ba_segment_gets_bonus(self, calc):
        """BA segments should get Club World bonus (+400 NTP)."""
        itin = _make_itinerary(
            [
                {"from": "LHR", "to": "JFK", "carrier": "BA"},
            ],
            origin="LHR",
        )
        results = calc.calculate(itin, booking_class="D", total_fare_usd=5000)
        est = results[0]
        assert est.method == NTPMethod.REVENUE
        # Should include the 400 bonus on top of the fare-based NTP
        assert est.estimated_ntp >= 400
        assert "bonus" in est.notes.lower()

    def test_ib_segment_is_revenue_based(self, calc):
        """IB segments should use revenue method."""
        itin = _make_itinerary(
            [
                {"from": "MEX", "to": "MAD", "carrier": "IB"},
            ]
        )
        results = calc.calculate(itin, booking_class="D", total_fare_usd=4000)
        est = results[0]
        assert est.method == NTPMethod.REVENUE
        assert est.confidence == "estimated"


# ------------------------------------------------------------------
# Surface and special segments
# ------------------------------------------------------------------


class TestSurfaceSegments:
    """Surface sectors earn zero NTP."""

    def test_surface_segment_zero_ntp(self, calc):
        """Surface segment should earn 0 NTP."""
        itin = _make_itinerary(
            [
                {"from": "JFK", "to": "MCO", "carrier": None, "type": "surface"},
            ]
        )
        results = calc.calculate(itin, booking_class="D")
        assert len(results) == 1
        est = results[0]
        assert est.estimated_ntp == 0.0
        assert est.distance_miles == 0.0
        assert "surface" in est.notes.lower()

    def test_surface_in_mixed_itinerary(self, calc):
        """Surface segment among flown segments still earns 0."""
        itin = _make_itinerary(
            [
                {"from": "DOH", "to": "NRT", "carrier": "QR"},
                {"from": "NRT", "to": "LAX", "carrier": None, "type": "surface"},
                {"from": "LAX", "to": "SFO", "carrier": "AA"},
            ]
        )
        results = calc.calculate(itin, booking_class="D", total_fare_usd=4000)
        assert len(results) == 3
        assert results[1].estimated_ntp == 0.0
        # Flown segments should have positive NTP
        assert results[0].estimated_ntp > 0
        assert results[2].estimated_ntp > 0


# ------------------------------------------------------------------
# Full V3 itinerary integration test
# ------------------------------------------------------------------


class TestV3Itinerary:
    """Integration test with the full V3 reference routing."""

    def test_v3_total_ntp_in_range(self, calc, v3_itinerary):
        """V3 total NTP should be in 6,000-12,000 range."""
        itin = Itinerary.model_validate(v3_itinerary)
        results = calc.calculate(itin, booking_class="D")

        total = sum(r.estimated_ntp for r in results)
        assert 6_000 <= total <= 12_000, f"Total NTP {total:.0f} outside 6,000-12,000"

    def test_v3_segment_count(self, calc, v3_itinerary):
        """Should produce one NTPEstimate per segment."""
        itin = Itinerary.model_validate(v3_itinerary)
        results = calc.calculate(itin, booking_class="D")
        assert len(results) == len(itin.segments)

    def test_v3_surface_segment_is_zero(self, calc, v3_itinerary):
        """JFK-MCO surface segment (index 11) should be 0 NTP."""
        itin = Itinerary.model_validate(v3_itinerary)
        results = calc.calculate(itin, booking_class="D")
        # Find the surface segment
        surface = [r for r in results if "surface" in r.notes.lower()]
        assert len(surface) == 1
        assert surface[0].estimated_ntp == 0.0

    def test_v3_distance_based_total(self, calc, v3_itinerary):
        """Distance-based segments should sum to ~7,300 NTP."""
        itin = Itinerary.model_validate(v3_itinerary)
        results = calc.calculate(itin, booking_class="D")

        distance_ntp = sum(r.estimated_ntp for r in results if r.method == NTPMethod.DISTANCE)
        # Expected ~7,331 from RJ + QR + JL + CX + FJ segments
        assert distance_ntp == pytest.approx(7_331, abs=200)

    def test_v3_has_both_methods(self, calc, v3_itinerary):
        """V3 should include both distance-based and revenue-based segments."""
        itin = Itinerary.model_validate(v3_itinerary)
        results = calc.calculate(itin, booking_class="D")

        methods = {r.method for r in results if r.estimated_ntp > 0}
        assert NTPMethod.DISTANCE in methods
        assert NTPMethod.REVENUE in methods


# ------------------------------------------------------------------
# Default fare lookup
# ------------------------------------------------------------------


class TestDefaultFare:
    """Fare lookup from fares.yaml."""

    def test_cai_done4_fare(self, calc):
        """CAI DONE4 fare should be 4000."""
        itin = _make_itinerary(
            [
                {"from": "CAI", "to": "AMM", "carrier": "RJ"},
            ],
            origin="CAI",
            ticket_type="DONE4",
        )
        # Should use the default fare without error
        results = calc.calculate(itin, booking_class="D")
        assert len(results) == 1
