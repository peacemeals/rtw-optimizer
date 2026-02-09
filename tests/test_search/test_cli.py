"""Tests for the search CLI command."""

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from rtw.cli import app
from rtw.search.models import (
    CandidateItinerary,
    Direction,
    RouteSegment,
    ScoredCandidate,
)
from rtw.models import (
    CabinClass,
    Itinerary,
    Segment,
    SegmentType,
    Ticket,
    TicketType,
)

runner = CliRunner()

FUTURE = (date.today() + timedelta(days=60)).isoformat()
FUTURE_END = (date.today() + timedelta(days=120)).isoformat()


def _mock_candidates(n=3):
    """Create mock CandidateItinerary list."""
    results = []
    for _ in range(n):
        segs = [
            Segment(**{"from": "SYD", "to": "NRT", "carrier": "JL", "type": "stopover"}),
            Segment(**{"from": "NRT", "to": "LHR", "carrier": "JL", "type": "stopover"}),
            Segment(**{"from": "LHR", "to": "JFK", "carrier": "BA", "type": "stopover"}),
            Segment(**{"from": "JFK", "to": "SYD", "carrier": "AA", "type": "stopover"}),
        ]
        itin = Itinerary(
            ticket=Ticket(type=TicketType.DONE3, cabin=CabinClass.BUSINESS, origin="SYD"),
            segments=segs,
        )
        route_segs = [
            RouteSegment(from_airport=s.from_airport, to_airport=s.to_airport, carrier=s.carrier)
            for s in segs
        ]
        results.append(CandidateItinerary(
            itinerary=itin, direction=Direction.EASTBOUND, route_segments=route_segs,
        ))
    return results


class TestSearchMissingArgs:
    def test_missing_cities(self):
        result = runner.invoke(app, [
            "search", "--from", FUTURE, "--to", FUTURE_END, "--origin", "SYD",
        ])
        assert result.exit_code == 2

    def test_missing_dates(self):
        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK", "--origin", "SYD",
        ])
        assert result.exit_code == 2

    def test_missing_origin(self):
        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK", "--from", FUTURE, "--to", FUTURE_END,
        ])
        assert result.exit_code == 2


class TestSearchWithMockedPipeline:
    @patch("rtw.search.generator.generate_candidates")
    @patch("rtw.search.query.parse_search_query")
    def test_no_candidates_exit_1(self, mock_parse, mock_gen):
        mock_parse.return_value = MagicMock()
        mock_gen.return_value = []
        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK",
            "--from", FUTURE, "--to", FUTURE_END,
            "--origin", "SYD", "--skip-availability", "--plain",
        ])
        assert result.exit_code == 1

    @patch("rtw.search.generator.generate_candidates")
    @patch("rtw.search.query.parse_search_query")
    def test_valid_search_plain(self, mock_parse, mock_gen):
        from rtw.search.models import SearchQuery
        from rtw.models import CabinClass, TicketType

        mock_parse.return_value = SearchQuery(
            cities=["LHR", "NRT", "JFK"], origin="SYD",
            date_from=date.today() + timedelta(days=60),
            date_to=date.today() + timedelta(days=120),
            cabin=CabinClass.BUSINESS, ticket_type=TicketType.DONE3,
        )
        mock_gen.return_value = _mock_candidates(3)

        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK",
            "--from", FUTURE, "--to", FUTURE_END,
            "--origin", "SYD", "--skip-availability", "--plain",
        ])
        assert result.exit_code == 0
        assert "Option 1" in result.output

    @patch("rtw.search.generator.generate_candidates")
    @patch("rtw.search.query.parse_search_query")
    def test_json_output(self, mock_parse, mock_gen):
        from rtw.search.models import SearchQuery
        import json

        mock_parse.return_value = SearchQuery(
            cities=["LHR", "NRT", "JFK"], origin="SYD",
            date_from=date.today() + timedelta(days=60),
            date_to=date.today() + timedelta(days=120),
            cabin=CabinClass.BUSINESS, ticket_type=TicketType.DONE3,
        )
        mock_gen.return_value = _mock_candidates(2)

        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK",
            "--from", FUTURE, "--to", FUTURE_END,
            "--origin", "SYD", "--skip-availability", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "options" in data

    @patch("rtw.search.generator.generate_candidates")
    @patch("rtw.search.query.parse_search_query")
    def test_export_option(self, mock_parse, mock_gen):
        from rtw.search.models import SearchQuery

        mock_parse.return_value = SearchQuery(
            cities=["LHR", "NRT", "JFK"], origin="SYD",
            date_from=date.today() + timedelta(days=60),
            date_to=date.today() + timedelta(days=120),
            cabin=CabinClass.BUSINESS, ticket_type=TicketType.DONE3,
        )
        mock_gen.return_value = _mock_candidates(3)

        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK",
            "--from", FUTURE, "--to", FUTURE_END,
            "--origin", "SYD", "--skip-availability", "--export", "1",
        ])
        assert result.exit_code == 0
        assert "ticket:" in result.output or "segments:" in result.output

    @patch("rtw.search.generator.generate_candidates")
    @patch("rtw.search.query.parse_search_query")
    def test_export_invalid_option_number(self, mock_parse, mock_gen):
        from rtw.search.models import SearchQuery

        mock_parse.return_value = SearchQuery(
            cities=["LHR", "NRT", "JFK"], origin="SYD",
            date_from=date.today() + timedelta(days=60),
            date_to=date.today() + timedelta(days=120),
            cabin=CabinClass.BUSINESS, ticket_type=TicketType.DONE3,
        )
        mock_gen.return_value = _mock_candidates(2)

        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK",
            "--from", FUTURE, "--to", FUTURE_END,
            "--origin", "SYD", "--skip-availability", "--export", "99",
        ])
        assert result.exit_code == 2


class TestSearchInputValidation:
    def test_invalid_date_format(self):
        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK",
            "--from", "not-a-date", "--to", FUTURE_END,
            "--origin", "SYD",
        ])
        assert result.exit_code == 2

    def test_bad_cabin_class(self):
        result = runner.invoke(app, [
            "search", "--cities", "LHR,NRT,JFK",
            "--from", FUTURE, "--to", FUTURE_END,
            "--origin", "SYD", "--cabin", "ultra_first",
        ])
        assert result.exit_code == 2
