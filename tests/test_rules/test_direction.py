"""Tests for direction and ocean crossing rules."""

from rtw.models import Itinerary, Ticket, Segment
from rtw.rules.direction import DirectionOfTravelRule, OceanCrossingRule
from rtw.validator import build_context


def _make_itinerary(segments_data):
    ticket = Ticket(type="DONE4", cabin="business", origin="CAI")
    segments = [Segment(**s) for s in segments_data]
    return Itinerary(ticket=ticket, segments=segments)


class TestDirectionOfTravel:
    def test_v3_eastbound_passes(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        ctx = build_context(itin)
        results = DirectionOfTravelRule().check(itin, ctx)
        assert all(r.passed for r in results)
        assert any("eastbound" in r.message for r in results)


class TestOceanCrossings:
    def test_v3_both_crossings(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        ctx = build_context(itin)
        results = OceanCrossingRule().check(itin, ctx)
        assert all(r.passed for r in results)

    def test_missing_pacific(self):
        # Only Atlantic crossing, no Pacific
        segs = [
            {"from": "CAI", "to": "AMM", "carrier": "RJ"},
            {"from": "AMM", "to": "JFK", "carrier": "QR"},  # TC2->TC1 Atlantic
            {"from": "JFK", "to": "LHR", "carrier": "BA"},  # TC1->TC2 Atlantic (2nd!)
            {"from": "LHR", "to": "CAI", "carrier": "BA"},
        ]
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = OceanCrossingRule().check(itin, ctx)
        pacific_results = [r for r in results if "Pacific" in r.message]
        assert any(not r.passed for r in pacific_results)

    def test_surface_crossing_not_counted(self):
        # Surface sector across ocean should not count
        segs = [
            {"from": "CAI", "to": "DOH", "carrier": "QR"},
            {"from": "DOH", "to": "NRT", "carrier": "QR"},  # TC2->TC3
            {"from": "NRT", "to": "LAX", "type": "surface"},  # Pacific but surface!
            {"from": "LAX", "to": "LHR", "carrier": "BA"},  # TC1->TC2 Atlantic
            {"from": "LHR", "to": "CAI", "carrier": "BA"},
        ]
        itin = _make_itinerary(segs)
        ctx = build_context(itin)
        results = OceanCrossingRule().check(itin, ctx)
        pacific_results = [r for r in results if "Pacific" in r.message]
        assert any(not r.passed for r in pacific_results)
