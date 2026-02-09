"""Integration tests for the complete search pipeline."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from rtw.models import CabinClass, TicketType
from rtw.search.generator import generate_candidates
from rtw.search.hubs import HubTable
from rtw.search.models import (
    AvailabilityStatus,
    CandidateItinerary,
    ScoredCandidate,
    SearchQuery,
    SearchResult,
)
from rtw.search.query import parse_search_query
from rtw.search.scorer import rank_candidates, score_candidates
from rtw.output.search_formatter import (
    format_search_json,
    format_search_results_plain,
    format_search_skeletons_plain,
)
from rtw.search.exporter import export_itinerary

FUTURE = date.today() + timedelta(days=60)
FUTURE_END = date.today() + timedelta(days=120)


class TestParseToGenerate:
    """Test query parsing flows into route generation."""

    def test_parse_then_generate_3_cities(self):
        query = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="business",
            ticket_type="DONE3",
        )
        candidates = generate_candidates(query)
        assert len(candidates) > 0
        for c in candidates:
            assert isinstance(c, CandidateItinerary)
            assert c.itinerary.segments[0].from_airport == "SYD"
            assert c.itinerary.segments[-1].to_airport == "SYD"

    def test_parse_then_generate_4_cities(self):
        query = parse_search_query(
            cities=["LHR", "NRT", "JFK", "HKG"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="business",
            ticket_type="DONE4",
        )
        candidates = generate_candidates(query)
        assert len(candidates) > 0

    def test_all_candidates_start_and_end_at_origin(self):
        query = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="business",
            ticket_type="DONE3",
        )
        candidates = generate_candidates(query)
        for c in candidates:
            segs = c.itinerary.segments
            assert segs[0].from_airport == "SYD"
            assert segs[-1].to_airport == "SYD"


class TestGenerateToScore:
    """Test candidates flow through scoring and ranking."""

    def test_score_and_rank_pipeline(self):
        query = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="business",
            ticket_type="DONE3",
        )
        candidates = generate_candidates(query)
        scored = [ScoredCandidate(candidate=c) for c in candidates]
        scored = score_candidates(scored, rank_by="availability")
        ranked = rank_candidates(scored, top_n=5)

        assert len(ranked) <= 5
        assert all(r.rank > 0 for r in ranked)
        # Scores should be descending
        scores = [r.composite_score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_different_rank_strategies(self):
        query = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="business",
            ticket_type="DONE3",
        )
        candidates = generate_candidates(query)
        scored = [ScoredCandidate(candidate=c) for c in candidates[:5]]

        for strategy in ["availability", "cost", "quality"]:
            result = score_candidates(scored, rank_by=strategy)
            ranked = rank_candidates(result)
            assert len(ranked) > 0


class TestScoreToDisplay:
    """Test scored results render correctly."""

    def test_plain_output_pipeline(self):
        query = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="business",
            ticket_type="DONE3",
        )
        candidates = generate_candidates(query)
        scored = [ScoredCandidate(candidate=c) for c in candidates[:3]]
        scored = score_candidates(scored)
        ranked = rank_candidates(scored, top_n=3)

        result = SearchResult(
            query=query, candidates_generated=len(candidates), options=ranked,
        )

        skeleton = format_search_skeletons_plain(result)
        assert "Option 1" in skeleton
        assert "SYD" in skeleton

        full = format_search_results_plain(result)
        assert len(full) > 0

    def test_json_output_pipeline(self):
        import json

        query = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="business",
            ticket_type="DONE3",
        )
        candidates = generate_candidates(query)
        scored = [ScoredCandidate(candidate=c) for c in candidates[:3]]
        scored = score_candidates(scored)
        ranked = rank_candidates(scored, top_n=3)

        result = SearchResult(
            query=query, candidates_generated=len(candidates), options=ranked,
        )

        json_str = format_search_json(result)
        data = json.loads(json_str)
        assert data["query"]["origin"] == "SYD"
        assert 0 < len(data["options"]) <= 3


class TestScoreToExport:
    """Test scored results export as valid YAML."""

    def test_export_pipeline(self):
        import yaml

        query = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="business",
            ticket_type="DONE3",
        )
        candidates = generate_candidates(query)
        scored = [ScoredCandidate(candidate=c) for c in candidates[:1]]
        scored = score_candidates(scored)
        ranked = rank_candidates(scored)

        yaml_str = export_itinerary(ranked[0], query)
        body = "\n".join(line for line in yaml_str.splitlines() if not line.startswith("#"))
        data = yaml.safe_load(body)
        assert data["ticket"]["origin"] == "SYD"
        assert len(data["segments"]) > 0


class TestEndToEndCLI:
    """Full CLI integration tests (no mocks except availability)."""

    def test_cli_search_skip_availability(self):
        from typer.testing import CliRunner
        from rtw.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "search",
            "--cities", "LHR,NRT,JFK",
            "--from", FUTURE.isoformat(),
            "--to", FUTURE_END.isoformat(),
            "--origin", "SYD",
            "--skip-availability",
            "--plain",
        ])
        assert result.exit_code == 0
        assert "Option 1" in result.output

    def test_cli_search_json(self):
        import json
        from typer.testing import CliRunner
        from rtw.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "search",
            "--cities", "LHR,NRT,JFK",
            "--from", FUTURE.isoformat(),
            "--to", FUTURE_END.isoformat(),
            "--origin", "SYD",
            "--skip-availability",
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "options" in data
        assert len(data["options"]) > 0

    def test_cli_search_export(self):
        import yaml
        from typer.testing import CliRunner
        from rtw.cli import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "search",
            "--cities", "LHR,NRT,JFK",
            "--from", FUTURE.isoformat(),
            "--to", FUTURE_END.isoformat(),
            "--origin", "SYD",
            "--skip-availability",
            "--export", "1",
        ])
        assert result.exit_code == 0
        # Should be parseable YAML
        body = "\n".join(line for line in result.output.splitlines() if not line.startswith("#"))
        data = yaml.safe_load(body)
        assert "ticket" in data
