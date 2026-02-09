"""Tests for search state persistence."""

import datetime
import json

import pytest

from rtw.models import CabinClass, Itinerary, Ticket, TicketType
from rtw.search.models import SearchQuery, SearchResult, ScoredCandidate, CandidateItinerary, Direction
from rtw.verify.state import SearchState


def _make_search_result(n_options=3):
    """Build a minimal SearchResult for testing."""
    query = SearchQuery(
        cities=["SYD", "HKG", "LHR", "JFK"],
        origin="SYD",
        date_from=datetime.date(2026, 9, 1),
        date_to=datetime.date(2026, 10, 15),
        cabin=CabinClass.BUSINESS,
        ticket_type=TicketType.DONE4,
    )
    ticket = Ticket(
        type=TicketType.DONE4,
        cabin=CabinClass.BUSINESS,
        origin="SYD",
    )
    options = []
    for i in range(n_options):
        itin = Itinerary(
            ticket=ticket,
            segments=[
                {"from": "SYD", "to": "HKG", "carrier": "CX"},
                {"from": "HKG", "to": "LHR", "carrier": "CX"},
                {"from": "LHR", "to": "JFK", "carrier": "BA"},
                {"from": "JFK", "to": "SYD", "carrier": "QF"},
            ],
        )
        candidate = CandidateItinerary(
            itinerary=itin,
            direction=Direction.EASTBOUND,
        )
        scored = ScoredCandidate(
            candidate=candidate,
            composite_score=90.0 - i * 10,
            rank=i + 1,
        )
        options.append(scored)

    return SearchResult(
        query=query,
        candidates_generated=10,
        options=options,
        base_fare_usd=6299.0,
    )


class TestSearchState:
    def test_save_and_load(self, tmp_path):
        state = SearchState(state_path=tmp_path / "state.json")
        result = _make_search_result()
        state.save(result)
        loaded = state.load()
        assert loaded is not None
        assert len(loaded.options) == 3
        assert loaded.query.origin == "SYD"
        assert loaded.base_fare_usd == 6299.0

    def test_load_missing(self, tmp_path):
        state = SearchState(state_path=tmp_path / "nope.json")
        assert state.load() is None

    def test_load_corrupted(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("not json at all")
        state = SearchState(state_path=path)
        assert state.load() is None

    def test_load_invalid_json(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"bad": "data"}))
        state = SearchState(state_path=path)
        assert state.load() is None

    def test_get_option(self, tmp_path):
        state = SearchState(state_path=tmp_path / "state.json")
        result = _make_search_result()
        state.save(result)
        # 1-based IDs
        opt1 = state.get_option(1)
        assert opt1 is not None
        assert opt1.rank == 1
        opt3 = state.get_option(3)
        assert opt3 is not None
        assert opt3.rank == 3

    def test_get_option_out_of_range(self, tmp_path):
        state = SearchState(state_path=tmp_path / "state.json")
        result = _make_search_result(n_options=2)
        state.save(result)
        assert state.get_option(0) is None  # 0 is invalid (1-based)
        assert state.get_option(3) is None  # Only 2 options
        assert state.get_option(-1) is None

    def test_state_age(self, tmp_path):
        state = SearchState(state_path=tmp_path / "state.json")
        result = _make_search_result()
        state.save(result)
        age = state.state_age_minutes()
        assert age is not None
        assert age < 1  # Just saved

    def test_option_count(self, tmp_path):
        state = SearchState(state_path=tmp_path / "state.json")
        assert state.option_count == 0
        result = _make_search_result(n_options=5)
        state.save(result)
        assert state.option_count == 5
