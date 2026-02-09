"""Tests for fare comparison logic, formatters, and CLI integration."""

import datetime
import json

import pytest

from rtw.cost import CostEstimator
from rtw.models import CabinClass, Itinerary, Segment, SegmentType, Ticket, TicketType
from rtw.search.fare_comparison import FareComparison, compute_fare_comparison
from rtw.search.models import (
    AvailabilityStatus,
    CandidateItinerary,
    Direction,
    RouteSegment,
    ScoredCandidate,
    SearchQuery,
    SearchResult,
    SegmentAvailability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_query(origin="SYD", ticket_type="DONE4"):
    return SearchQuery(
        cities=["LHR", "NRT", "JFK"],
        origin=origin,
        date_from=datetime.date(2026, 9, 1),
        date_to=datetime.date(2026, 11, 15),
        cabin=CabinClass.BUSINESS,
        ticket_type=TicketType(ticket_type),
    )


def _make_candidate(segments_spec, direction=Direction.EASTBOUND):
    """Build a ScoredCandidate from a list of segment specs.

    Each spec is a tuple: (from, to, carrier, price_usd_or_None, is_surface)
    """
    itin_segments = []
    route_segments = []
    for from_apt, to_apt, carrier, price, is_surface in segments_spec:
        seg_type = SegmentType.SURFACE if is_surface else SegmentType.STOPOVER
        itin_segments.append(Segment(
            from_airport=from_apt,
            to_airport=to_apt,
            carrier=carrier if not is_surface else None,
            type=seg_type,
        ))
        avail = None
        if not is_surface and price is not None:
            avail = SegmentAvailability(
                status=AvailabilityStatus.AVAILABLE,
                price_usd=price,
            )
        elif not is_surface:
            avail = SegmentAvailability(status=AvailabilityStatus.UNKNOWN)
        route_segments.append(RouteSegment(
            from_airport=from_apt,
            to_airport=to_apt,
            carrier=carrier or "XX",
            segment_type=seg_type,
            availability=avail,
        ))

    ticket = Ticket(type=TicketType.DONE4, cabin=CabinClass.BUSINESS, origin="SYD")
    itinerary = Itinerary(ticket=ticket, segments=itin_segments)
    cand = CandidateItinerary(
        itinerary=itinerary,
        direction=direction,
        route_segments=route_segments,
    )
    return ScoredCandidate(candidate=cand)


# ---------------------------------------------------------------------------
# 1. Fare Lookup Tests (~8 tests)
# ---------------------------------------------------------------------------

class TestFareLookup:
    def test_fare_lookup_known_origin_done4(self):
        e = CostEstimator()
        assert e.get_base_fare("SYD", TicketType.DONE4) == 8800.0

    def test_fare_lookup_known_origin_done3(self):
        e = CostEstimator()
        assert e.get_base_fare("CAI", TicketType.DONE3) == 3500.0

    def test_fare_lookup_high_fare(self):
        e = CostEstimator()
        assert e.get_base_fare("JFK", TicketType.DONE6) == 14099.0

    def test_fare_lookup_economy(self):
        e = CostEstimator()
        assert e.get_base_fare("OSL", TicketType.LONE4) == 3000.0

    def test_fare_lookup_unknown_origin(self):
        e = CostEstimator()
        assert e.get_base_fare("BOM", TicketType.DONE4) == 0.0

    def test_fare_lookup_unknown_ticket_type(self):
        e = CostEstimator()
        # AONE4 doesn't exist in our data
        result = e.get_base_fare("SYD", TicketType("AONE4"))
        assert result == 0.0

    def test_fare_lookup_case_insensitive(self):
        e = CostEstimator()
        # get_base_fare uppercases the origin
        assert e.get_base_fare("syd", TicketType.DONE4) == 8800.0

    def test_all_origins_have_done_and_lone_types(self):
        e = CostEstimator()
        import yaml
        from pathlib import Path
        with open(Path(__file__).parent.parent / "rtw" / "data" / "fares.yaml") as f:
            fares = yaml.safe_load(f)
        for origin in fares.get("origins", {}):
            for tt in ["DONE3", "DONE4", "DONE5", "DONE6", "LONE3", "LONE4", "LONE5", "LONE6"]:
                fare = e.get_base_fare(origin, TicketType(tt))
                assert isinstance(fare, float), f"{origin}/{tt} should return float"


# ---------------------------------------------------------------------------
# 2. Segment Price Aggregation Tests (~6 tests)
# ---------------------------------------------------------------------------

class TestSegmentAggregation:
    def test_aggregate_all_prices_present(self):
        spec = [
            ("SYD", "HKG", "CX", 500.0, False),
            ("HKG", "LHR", "CX", 500.0, False),
            ("LHR", "JFK", "BA", 500.0, False),
            ("JFK", "SYD", "QF", 500.0, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.segment_total_usd == 2000.0
        assert fc.segments_priced == 4
        assert fc.segments_total == 4

    def test_aggregate_some_prices_none(self):
        spec = [
            ("SYD", "HKG", "CX", 500.0, False),
            ("HKG", "LHR", "CX", None, False),
            ("LHR", "JFK", "BA", 500.0, False),
            ("JFK", "SYD", "QF", None, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.segment_total_usd == 1000.0
        assert fc.segments_priced == 2
        assert fc.segments_total == 4

    def test_aggregate_no_prices(self):
        spec = [
            ("SYD", "HKG", "CX", None, False),
            ("HKG", "LHR", "CX", None, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.segment_total_usd == 0.0
        assert fc.segments_priced == 0

    def test_aggregate_skips_surface_segments(self):
        spec = [
            ("SYD", "HKG", "CX", 500.0, False),
            ("HKG", "BKK", "XX", None, True),  # surface
            ("BKK", "LHR", "QR", 600.0, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.segment_total_usd == 1100.0
        assert fc.segments_priced == 2
        assert fc.segments_total == 2  # surface excluded from total

    def test_aggregate_single_segment(self):
        spec = [("SYD", "LHR", "QF", 3000.0, False)]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.segment_total_usd == 3000.0
        assert fc.segments_priced == 1

    def test_aggregate_zero_price_excluded(self):
        spec = [
            ("SYD", "HKG", "CX", 0.0, False),  # Google Flights error
            ("HKG", "LHR", "CX", 500.0, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.segment_total_usd == 500.0
        assert fc.segments_priced == 1
        assert fc.segments_total == 2


# ---------------------------------------------------------------------------
# 3. Value Calculation Tests (~8 tests)
# ---------------------------------------------------------------------------

class TestValueCalculation:
    def test_value_positive_savings(self):
        # RTW $8,800, individual $22,000 -> savings $13,200, multiplier 2.5x
        spec = [
            ("SYD", "HKG", "CX", 5500.0, False),
            ("HKG", "LHR", "CX", 5500.0, False),
            ("LHR", "JFK", "BA", 5500.0, False),
            ("JFK", "SYD", "QF", 5500.0, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.savings_usd == 13200.0
        assert fc.value_multiplier == 2.5

    def test_value_negative_savings(self):
        # RTW $8,800, individual $5,000 -> savings -$3,800
        spec = [
            ("SYD", "HKG", "CX", 1250.0, False),
            ("HKG", "LHR", "CX", 1250.0, False),
            ("LHR", "JFK", "BA", 1250.0, False),
            ("JFK", "SYD", "QF", 1250.0, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.savings_usd == -3800.0
        assert fc.value_multiplier == 0.57

    def test_value_breakeven(self):
        # RTW $8,800, individual $8,800 -> savings $0, multiplier 1.0x
        spec = [
            ("SYD", "HKG", "CX", 2200.0, False),
            ("HKG", "LHR", "CX", 2200.0, False),
            ("LHR", "JFK", "BA", 2200.0, False),
            ("JFK", "SYD", "QF", 2200.0, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.savings_usd == 0.0
        assert fc.value_multiplier == 1.0

    def test_value_rtw_fare_zero(self):
        spec = [("SYD", "HKG", "CX", 5000.0, False)]
        cand = _make_candidate(spec)
        query = _make_query(origin="BOM")  # BOM not in fares.yaml
        fc = compute_fare_comparison(cand, query)
        assert fc.base_fare_usd == 0.0
        assert fc.value_multiplier == 0.0  # no division by zero

    def test_value_no_prices(self):
        spec = [
            ("SYD", "HKG", "CX", None, False),
            ("HKG", "LHR", "CX", None, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.savings_usd == 0.0
        assert fc.value_multiplier == 0.0

    def test_value_partial_prices(self):
        spec = [
            ("SYD", "HKG", "CX", 3000.0, False),
            ("HKG", "DEL", "CX", 2000.0, False),
            ("DEL", "LHR", "QR", None, False),
            ("LHR", "JFK", "BA", 1000.0, False),
            ("JFK", "SYD", "QF", None, False),
        ]
        cand = _make_candidate(spec)
        fc = compute_fare_comparison(cand, _make_query())
        assert fc.segments_priced == 3
        assert fc.segments_total == 5

    def test_value_large_multiplier(self):
        # CAI $3,500 vs $35,000 -> multiplier 10.0x
        spec = [
            ("CAI", "HKG", "QR", 10000.0, False),
            ("HKG", "SYD", "CX", 10000.0, False),
            ("SYD", "LAX", "QF", 10000.0, False),
            ("LAX", "CAI", "BA", 5000.0, False),
        ]
        cand = _make_candidate(spec)
        query = _make_query(origin="CAI", ticket_type="DONE3")
        fc = compute_fare_comparison(cand, query)
        assert fc.value_multiplier == 10.0
        assert fc.verdict == "excellent"

    def test_value_verdict_thresholds(self):
        fc = FareComparison(value_multiplier=3.0, segments_priced=1)
        assert fc.verdict == "excellent"
        fc = FareComparison(value_multiplier=2.0, segments_priced=1)
        assert fc.verdict == "great"
        fc = FareComparison(value_multiplier=1.5, segments_priced=1)
        assert fc.verdict == "good"
        fc = FareComparison(value_multiplier=1.0, segments_priced=1)
        assert fc.verdict == "fair"
        fc = FareComparison(value_multiplier=0.5, segments_priced=1)
        assert fc.verdict == "poor"


# ---------------------------------------------------------------------------
# 4. Output Format Tests (~12 tests)
# ---------------------------------------------------------------------------

def _make_result_with_fare(segments_spec=None, origin="SYD", ticket_type="DONE4"):
    if segments_spec is None:
        segments_spec = [
            ("SYD", "HKG", "CX", 5000.0, False),
            ("HKG", "LHR", "CX", 6000.0, False),
            ("LHR", "JFK", "BA", 4000.0, False),
            ("JFK", "SYD", "QF", 7000.0, False),
        ]
    query = _make_query(origin=origin, ticket_type=ticket_type)
    cand = _make_candidate(segments_spec)
    cand.fare_comparison = compute_fare_comparison(cand, query)
    cand.rank = 1
    e = CostEstimator()
    return SearchResult(
        query=query,
        candidates_generated=10,
        options=[cand],
        base_fare_usd=e.get_base_fare(query.origin, query.ticket_type),
    )


class TestPlainOutput:
    def test_plain_contains_rtw_fare(self):
        from rtw.output.search_formatter import format_search_results_plain
        result = _make_result_with_fare()
        output = format_search_results_plain(result)
        assert "$8,800" in output

    def test_plain_contains_savings(self):
        from rtw.output.search_formatter import format_search_results_plain
        result = _make_result_with_fare()
        output = format_search_results_plain(result)
        assert "savings" in output.lower() or "Savings" in output

    def test_plain_no_value_when_no_prices(self):
        from rtw.output.search_formatter import format_search_results_plain
        spec = [
            ("SYD", "HKG", "CX", None, False),
            ("HKG", "LHR", "CX", None, False),
        ]
        result = _make_result_with_fare(segments_spec=spec)
        output = format_search_results_plain(result)
        assert "savings" not in output.lower()


class TestRichOutput:
    def test_rich_contains_fare_data(self):
        from rtw.output.search_formatter import format_search_results_rich
        result = _make_result_with_fare()
        output = format_search_results_rich(result)
        # Rich inserts ANSI codes that can split formatted numbers
        assert "RTW Fare" in output

    def test_rich_positive_savings_has_style(self):
        from rtw.output.search_formatter import format_search_results_rich
        result = _make_result_with_fare()
        output = format_search_results_rich(result)
        # Should contain the verdict text
        assert "GREAT" in output or "EXCELLENT" in output or "GOOD" in output

    def test_rich_negative_savings_verdict(self):
        from rtw.output.search_formatter import format_search_results_rich
        spec = [
            ("SYD", "HKG", "CX", 1000.0, False),
            ("HKG", "LHR", "CX", 1000.0, False),
        ]
        result = _make_result_with_fare(segments_spec=spec)
        output = format_search_results_rich(result)
        assert "POOR" in output


class TestJsonOutput:
    def test_json_parseable(self):
        from rtw.output.search_formatter import format_search_json
        result = _make_result_with_fare()
        data = json.loads(format_search_json(result))
        assert "options" in data

    def test_json_contains_fare_comparison(self):
        from rtw.output.search_formatter import format_search_json
        result = _make_result_with_fare()
        data = json.loads(format_search_json(result))
        fc = data["options"][0]["fare_comparison"]
        assert fc["rtw_base_fare_usd"] == 8800.0
        assert isinstance(fc["segment_total_usd"], float)
        assert isinstance(fc["segments_priced"], int)
        assert fc["verdict"] in ("excellent", "great", "good", "fair", "poor")

    def test_json_is_complete_flag(self):
        from rtw.output.search_formatter import format_search_json
        result = _make_result_with_fare()
        data = json.loads(format_search_json(result))
        fc = data["options"][0]["fare_comparison"]
        assert fc["is_complete"] is True

    def test_json_no_fare_comparison_when_none(self):
        from rtw.output.search_formatter import format_search_json
        query = _make_query()
        cand = _make_candidate([("SYD", "HKG", "CX", None, False)])
        cand.rank = 1
        # fare_comparison is None (not computed)
        result = SearchResult(query=query, candidates_generated=1, options=[cand])
        data = json.loads(format_search_json(result))
        assert "fare_comparison" not in data["options"][0]


class TestYamlExport:
    def test_yaml_contains_fare_header(self):
        from rtw.search.exporter import export_itinerary
        result = _make_result_with_fare()
        opt = result.options[0]
        output = export_itinerary(opt, result.query)
        assert "# RTW Fare:" in output
        assert "$8,800" in output

    def test_yaml_no_fare_header_when_unavailable(self):
        from rtw.search.exporter import export_itinerary
        query = _make_query(origin="BOM")
        cand = _make_candidate([("BOM", "HKG", "CX", None, False)])
        cand.fare_comparison = compute_fare_comparison(cand, query)
        output = export_itinerary(cand, query)
        assert "# RTW Fare:" not in output
