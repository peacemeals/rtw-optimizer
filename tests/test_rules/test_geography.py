"""Tests for geography rules."""

from rtw.models import Itinerary, Ticket, Segment
from rtw.rules.geography import HawaiiAlaskaRule, TranscontinentalUSRule
from rtw.validator import build_context


def _make_itinerary(segments_data):
    ticket = Ticket(type="DONE4", cabin="business", origin="CAI")
    segments = [Segment(**s) for s in segments_data]
    return Itinerary(ticket=ticket, segments=segments)


class TestHawaiiAlaska:
    def test_v3_passes(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        ctx = build_context(itin)
        results = HawaiiAlaskaRule().check(itin, ctx)
        assert all(r.passed for r in results)

    def test_hawaii_backtrack_fails(self):
        segs = [
            {"from": "LAX", "to": "HNL", "carrier": "AA"},
            {"from": "HNL", "to": "LAX", "carrier": "AA"},
            {"from": "LAX", "to": "HNL", "carrier": "AA"},  # Backtrack!
        ]
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = HawaiiAlaskaRule().check(itin, ctx)
        assert any(not r.passed for r in results)


class TestTranscontinentalUS:
    def test_v3_passes(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        ctx = build_context(itin)
        results = TranscontinentalUSRule().check(itin, ctx)
        assert all(r.passed for r in results)

    def test_two_transcon_fails(self):
        segs = [
            {"from": "JFK", "to": "LAX", "carrier": "AA"},
            {"from": "LAX", "to": "JFK", "carrier": "AA"},  # 2nd transcon
        ]
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = TranscontinentalUSRule().check(itin, ctx)
        assert any(not r.passed for r in results)
