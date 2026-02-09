"""CLI tests for login, verify, and --verify-dclass commands."""

import datetime
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from rtw.cli import app

runner = CliRunner()


class TestLoginHelp:
    """Test login sub-app help output."""

    def test_login_help(self):
        result = runner.invoke(app, ["login", "--help"])
        assert result.exit_code == 0
        assert "expertflyer" in result.output

    def test_login_expertflyer_help(self):
        result = runner.invoke(app, ["login", "expertflyer", "--help"])
        assert result.exit_code == 0
        assert "ExpertFlyer" in result.output
        assert "credential" in result.output.lower()

    def test_login_status_help(self):
        result = runner.invoke(app, ["login", "status", "--help"])
        assert result.exit_code == 0

    def test_login_clear_help(self):
        result = runner.invoke(app, ["login", "clear", "--help"])
        assert result.exit_code == 0


class TestLoginStatus:
    """Test login status command."""

    @patch("rtw.cli.keyring", create=True)
    def test_status_no_credentials(self, mock_keyring):
        mock_keyring.get_password = MagicMock(return_value=None)

        # Need to patch the import inside the function
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = runner.invoke(app, ["login", "status"])
        assert result.exit_code == 0
        assert "not configured" in result.output

    @patch("rtw.cli.keyring", create=True)
    def test_status_has_credentials(self, mock_keyring):
        def fake_get(service, key):
            return {"username": "test@test.com", "password": "secret"}.get(key)

        mock_keyring.get_password = fake_get

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = runner.invoke(app, ["login", "status"])
        assert result.exit_code == 0
        assert "configured" in result.output

    @patch("rtw.cli.keyring", create=True)
    def test_status_json(self, mock_keyring):
        def fake_get(service, key):
            return {"username": "user@test.com", "password": "pw"}.get(key)

        mock_keyring.get_password = fake_get

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = runner.invoke(app, ["login", "status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["has_credentials"] is True
        assert data["username"] == "user@test.com"


class TestLoginClear:
    """Test login clear command."""

    def test_clear(self):
        mock_keyring = MagicMock()
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = runner.invoke(app, ["login", "clear"])
        assert result.exit_code == 0
        assert "cleared" in result.output


class TestVerifyHelp:
    """Test verify command help."""

    def test_verify_help(self):
        result = runner.invoke(app, ["verify", "--help"])
        assert result.exit_code == 0
        assert "D-class" in result.output
        assert "ExpertFlyer" in result.output


class TestVerifyNoState:
    """Test verify command without prior search."""

    @patch("rtw.verify.state.SearchState")
    def test_verify_no_state(self, mock_state_cls):
        state = MagicMock()
        state.load.return_value = None
        mock_state_cls.return_value = state

        result = runner.invoke(app, ["verify"])
        assert result.exit_code == 1
        assert "No saved search" in result.output or result.exit_code == 1


class TestVerifyNoCreds:
    """Test verify command without ExpertFlyer credentials."""

    @patch("rtw.scraper.expertflyer._get_credentials", return_value=None)
    @patch("rtw.verify.state.SearchState")
    def test_verify_no_creds(self, mock_state_cls, mock_creds):
        from rtw.models import CabinClass, Itinerary, Ticket, TicketType
        from rtw.search.models import (
            CandidateItinerary, Direction, ScoredCandidate, SearchQuery, SearchResult,
        )

        query = SearchQuery(
            cities=["SYD", "HKG", "LHR", "JFK"],
            origin="SYD",
            date_from=datetime.date(2026, 9, 1),
            date_to=datetime.date(2026, 10, 15),
            cabin=CabinClass.BUSINESS,
            ticket_type=TicketType.DONE4,
        )
        ticket = Ticket(type=TicketType.DONE4, cabin=CabinClass.BUSINESS, origin="SYD")
        itin = Itinerary(
            ticket=ticket,
            segments=[
                {"from": "SYD", "to": "HKG", "carrier": "CX"},
            ],
        )
        candidate = CandidateItinerary(itinerary=itin, direction=Direction.EASTBOUND)
        scored = ScoredCandidate(candidate=candidate, rank=1)
        sr = SearchResult(
            query=query, candidates_generated=1, options=[scored], base_fare_usd=6299.0,
        )

        state = MagicMock()
        state.load.return_value = sr
        state.state_age_minutes.return_value = 5.0
        mock_state_cls.return_value = state

        result = runner.invoke(app, ["verify"])
        assert result.exit_code == 1
        assert "credential" in result.output.lower() or "login" in result.output.lower()


class TestScoredToVerifyOption:
    """Test the conversion helper."""

    def test_conversion(self):
        from rtw.cli import _scored_to_verify_option
        from rtw.models import CabinClass, Itinerary, Ticket, TicketType
        from rtw.search.models import CandidateItinerary, Direction, ScoredCandidate

        ticket = Ticket(type=TicketType.DONE4, cabin=CabinClass.BUSINESS, origin="SYD")
        itin = Itinerary(
            ticket=ticket,
            segments=[
                {"from": "SYD", "to": "HKG", "carrier": "CX", "type": "stopover"},
                {"from": "HKG", "to": "BKK", "type": "surface"},
                {"from": "BKK", "to": "LHR", "carrier": "BA", "type": "stopover"},
            ],
        )
        candidate = CandidateItinerary(itinerary=itin, direction=Direction.EASTBOUND)
        scored = ScoredCandidate(candidate=candidate, rank=1)

        option = _scored_to_verify_option(scored, 1)
        assert option.option_id == 1
        assert len(option.segments) == 3
        assert option.segments[0].segment_type == "FLOWN"
        assert option.segments[0].origin == "SYD"
        assert option.segments[0].destination == "HKG"
        assert option.segments[0].carrier == "CX"
        assert option.segments[1].segment_type == "SURFACE"
        assert option.segments[2].segment_type == "FLOWN"
        assert option.segments[2].carrier == "BA"


class TestDisplayVerifyResult:
    """Test _display_verify_result shows per-flight sub-rows."""

    def _make_verify_result(self):
        from rtw.verify.models import (
            DClassResult, DClassStatus, FlightAvailability,
            SegmentVerification, VerifyResult,
        )
        flights = [
            FlightAvailability(carrier="CX", flight_number="CX252", seats=9,
                               depart_time="03/10/26 11:00 AM", aircraft="77W"),
            FlightAvailability(carrier="CX", flight_number="CX254", seats=6,
                               depart_time="03/10/26 10:05 PM", aircraft="77W"),
            FlightAvailability(carrier="CX", flight_number="CX256", seats=0,
                               depart_time="03/10/26 8:15 PM", aircraft="359"),
        ]
        dclass = DClassResult(
            status=DClassStatus.AVAILABLE, seats=9, carrier="CX",
            origin="LHR", destination="HKG",
            target_date=datetime.date(2026, 3, 10),
            flights=flights,
        )
        seg = SegmentVerification(
            index=0, segment_type="FLOWN", origin="LHR", destination="HKG",
            carrier="CX", target_date=datetime.date(2026, 3, 10), dclass=dclass,
        )
        return VerifyResult(option_id=1, segments=[seg])

    def test_display_code_in_output(self, capsys):
        from rtw.cli import _display_verify_result
        result = self._make_verify_result()
        _display_verify_result(result)
        captured = capsys.readouterr()
        # Rich output goes to stderr
        assert "D9" in captured.err
        assert "2 avl" in captured.err

    def test_per_flight_rows_shown(self, capsys):
        from rtw.cli import _display_verify_result
        result = self._make_verify_result()
        _display_verify_result(result)
        captured = capsys.readouterr()
        assert "CX252" in captured.err
        assert "CX254" in captured.err

    def test_d0_count_shown(self, capsys):
        from rtw.cli import _display_verify_result
        result = self._make_verify_result()
        _display_verify_result(result)
        captured = capsys.readouterr()
        assert "1 more at D0" in captured.err

    def test_tight_badge(self, capsys):
        from rtw.cli import _display_verify_result
        result = self._make_verify_result()
        _display_verify_result(result)
        captured = capsys.readouterr()
        # 2 available flights → TIGHT badge
        assert "TIGHT" in captured.err

    def test_quiet_hides_subrows(self, capsys):
        from rtw.cli import _display_verify_result
        result = self._make_verify_result()
        _display_verify_result(result, quiet=True)
        captured = capsys.readouterr()
        # Should still show summary but not per-flight detail
        assert "D9" in captured.err
        assert "CX252" not in captured.err
