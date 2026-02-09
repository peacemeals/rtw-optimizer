"""Tests for search output formatters."""

from datetime import date, timedelta

import json as json_mod

import pytest

from rtw.models import (
    CabinClass,
    Itinerary,
    Segment,
    SegmentType,
    Ticket,
    TicketType,
)
from rtw.output.search_formatter import (
    format_search_json,
    format_search_results_plain,
    format_search_results_rich,
    format_search_skeletons_plain,
    format_search_skeletons_rich,
)
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

FUTURE = date.today() + timedelta(days=60)
FUTURE_END = date.today() + timedelta(days=120)


def _make_result(num_options=2, num_segs=3) -> SearchResult:
    query = SearchQuery(
        cities=["LHR", "NRT", "JFK"],
        origin="SYD",
        date_from=FUTURE,
        date_to=FUTURE_END,
        cabin=CabinClass.BUSINESS,
        ticket_type=TicketType.DONE3,
    )
    options = []
    for rank in range(1, num_options + 1):
        segs = [
            Segment(**{"from": "AAA", "to": "BBB", "carrier": "AA", "type": "stopover"})
            for _ in range(num_segs)
        ]
        itin = Itinerary(
            ticket=Ticket(type=TicketType.DONE3, cabin=CabinClass.BUSINESS, origin="SYD"),
            segments=segs,
        )
        route_segs = [
            RouteSegment(
                from_airport="AAA", to_airport="BBB", carrier="AA",
                availability=SegmentAvailability(
                    status=AvailabilityStatus.AVAILABLE, price_usd=500.0,
                ),
            )
            for _ in range(num_segs)
        ]
        cand = CandidateItinerary(
            itinerary=itin, direction=Direction.EASTBOUND, route_segments=route_segs,
        )
        options.append(ScoredCandidate(
            candidate=cand, composite_score=90.0 - rank * 5, rank=rank,
            estimated_cost_usd=1000.0 * rank,
        ))

    return SearchResult(
        query=query, candidates_generated=50, options=options,
    )


class TestSkeletonFormatters:
    def test_plain_contains_option_headers(self):
        result = _make_result()
        output = format_search_skeletons_plain(result)
        assert "Option 1" in output
        assert "Option 2" in output

    def test_plain_contains_candidate_count(self):
        result = _make_result()
        output = format_search_skeletons_plain(result)
        assert "50 candidates" in output

    def test_plain_contains_segment_count(self):
        result = _make_result(num_segs=5)
        output = format_search_skeletons_plain(result)
        assert "5 segments" in output

    def test_rich_returns_string(self):
        result = _make_result()
        output = format_search_skeletons_rich(result)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_rich_contains_option_info(self):
        result = _make_result()
        output = format_search_skeletons_rich(result)
        # Rich adds color codes between "Option " and "1"
        assert "Option" in output


class TestResultFormatters:
    def test_plain_contains_availability(self):
        result = _make_result()
        output = format_search_results_plain(result)
        assert "AVAILABLE" in output

    def test_plain_contains_route_info(self):
        result = _make_result()
        output = format_search_results_plain(result)
        assert "AAA-BBB" in output

    def test_rich_returns_string(self):
        result = _make_result()
        output = format_search_results_rich(result)
        assert isinstance(output, str)
        assert len(output) > 0


class TestJsonFormatter:
    def test_json_is_valid(self):
        result = _make_result()
        output = format_search_json(result)
        data = json_mod.loads(output)
        assert "query" in data
        assert "summary" in data
        assert "options" in data

    def test_json_option_count(self):
        result = _make_result(num_options=3)
        output = format_search_json(result)
        data = json_mod.loads(output)
        assert len(data["options"]) == 3

    def test_json_segment_data(self):
        result = _make_result()
        output = format_search_json(result)
        data = json_mod.loads(output)
        seg = data["options"][0]["segments"][0]
        assert seg["from"] == "AAA"
        assert seg["to"] == "BBB"
        assert seg["carrier"] == "AA"
        assert seg["availability"] == "available"

    def test_json_query_data(self):
        result = _make_result()
        output = format_search_json(result)
        data = json_mod.loads(output)
        assert data["query"]["origin"] == "SYD"
        assert data["query"]["cabin"] == "business"

    def test_json_summary(self):
        result = _make_result()
        output = format_search_json(result)
        data = json_mod.loads(output)
        assert data["summary"]["candidates_generated"] == 50
        assert data["summary"]["valid_options"] == 2

    def test_json_cost_included(self):
        result = _make_result()
        output = format_search_json(result)
        data = json_mod.loads(output)
        assert data["options"][0]["estimated_cost_usd"] > 0


class TestEmptyResults:
    def test_plain_skeleton_no_options(self):
        query = SearchQuery(
            cities=["LHR", "NRT", "JFK"], origin="SYD",
            date_from=FUTURE, date_to=FUTURE_END,
            cabin=CabinClass.BUSINESS, ticket_type=TicketType.DONE3,
        )
        result = SearchResult(query=query, candidates_generated=0, options=[])
        output = format_search_skeletons_plain(result)
        assert "0 candidates" in output

    def test_json_empty_options(self):
        query = SearchQuery(
            cities=["LHR", "NRT", "JFK"], origin="SYD",
            date_from=FUTURE, date_to=FUTURE_END,
            cabin=CabinClass.BUSINESS, ticket_type=TicketType.DONE3,
        )
        result = SearchResult(query=query, candidates_generated=0, options=[])
        output = format_search_json(result)
        data = json_mod.loads(output)
        assert data["options"] == []
