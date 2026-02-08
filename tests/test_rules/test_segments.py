"""Tests for segment and continent limit rules."""

from rtw.models import Itinerary, Ticket, Segment, Severity
from rtw.rules.segments import SegmentCountRule, PerContinentLimitRule
from rtw.validator import build_context


def _make_itinerary(segments_data: list[dict], ticket_type="DONE4") -> Itinerary:
    """Helper to build itinerary from segment dicts."""
    ticket = Ticket(type=ticket_type, cabin="business", origin="CAI")
    segments = [Segment(**s) for s in segments_data]
    return Itinerary(ticket=ticket, segments=segments)


class TestSegmentCount:
    def test_valid_16_segments(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        ctx = build_context(itin)
        results = SegmentCountRule().check(itin, ctx)
        assert all(r.passed for r in results)

    def test_too_many_segments(self):
        segs = [{"from": "CAI", "to": "AMM", "carrier": "RJ"}] * 17
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = SegmentCountRule().check(itin, ctx)
        assert any(not r.passed for r in results)
        assert "17" in results[0].message

    def test_too_few_segments(self):
        segs = [{"from": "CAI", "to": "AMM", "carrier": "RJ"}] * 2
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = SegmentCountRule().check(itin, ctx)
        assert any(not r.passed for r in results)

    def test_minimum_3_passes(self):
        segs = [{"from": "CAI", "to": "AMM", "carrier": "RJ"}] * 3
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = SegmentCountRule().check(itin, ctx)
        assert all(r.passed for r in results)


class TestPerContinentLimit:
    def test_v3_passes(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        ctx = build_context(itin)
        results = PerContinentLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed and r.severity == Severity.VIOLATION]
        assert len(violations) == 0

    def test_5_eu_me_segments_fails(self):
        # 5 segments all in EU/ME should fail (limit is 4)
        segs = [
            {"from": "CAI", "to": "AMM", "carrier": "RJ"},
            {"from": "AMM", "to": "DOH", "carrier": "QR"},
            {"from": "DOH", "to": "IST", "carrier": "QR"},
            {"from": "IST", "to": "MAD", "carrier": "IB"},
            {"from": "MAD", "to": "CAI", "carrier": "IB"},
        ]
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = PerContinentLimitRule().check(itin, ctx)
        eu_me_results = [r for r in results if "EU_ME" in r.message]
        assert any(not r.passed for r in eu_me_results)

    def test_na_allows_6(self):
        # 6 segments in NA should be fine (limit is 6)
        segs = [
            {"from": "JFK", "to": "LAX", "carrier": "AA"},
            {"from": "LAX", "to": "SFO", "carrier": "AA"},
            {"from": "SFO", "to": "DFW", "carrier": "AA"},
            {"from": "DFW", "to": "MIA", "carrier": "AA"},
            {"from": "MIA", "to": "MCO", "carrier": "AA"},
            {"from": "MCO", "to": "JFK", "carrier": "AA"},
        ]
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = PerContinentLimitRule().check(itin, ctx)
        na_results = [r for r in results if "N_America" in r.message]
        assert all(r.passed for r in na_results)
