"""Tests for output formatters (T040)."""

import json
import re

import pytest

from rtw.booking import BookingGenerator, BookingScript
from rtw.models import (
    CostEstimate,
    Itinerary,
    NTPEstimate,
    NTPMethod,
    RuleResult,
    SegmentValue,
    Severity,
    TicketType,
    ValidationReport,
)
from rtw.output import get_formatter
from rtw.output.json_formatter import JsonFormatter
from rtw.output.plain_formatter import PlainFormatter
from rtw.output.rich_formatter import RichFormatter


# --- Fixtures ---


@pytest.fixture
def v3(v3_itinerary):
    """Parse V3 fixture into an Itinerary model."""
    return Itinerary(**v3_itinerary)


@pytest.fixture
def validation_report(v3) -> ValidationReport:
    """Create a realistic validation report with mixed results."""
    results = [
        RuleResult(
            rule_id="R001",
            rule_name="Origin Return",
            passed=True,
            severity=Severity.VIOLATION,
            message="Itinerary returns to origin CAI.",
        ),
        RuleResult(
            rule_id="R002",
            rule_name="Segment Limit",
            passed=True,
            severity=Severity.VIOLATION,
            message="15 flown segments within 16 limit.",
        ),
        RuleResult(
            rule_id="R003",
            rule_name="Continent Count",
            passed=True,
            severity=Severity.VIOLATION,
            message="4 continents visited, matches DONE4.",
        ),
        RuleResult(
            rule_id="R004",
            rule_name="Backtracking",
            passed=False,
            severity=Severity.WARNING,
            message="NAN-FUN-NAN appears to backtrack within SWP.",
            fix_suggestion="Acceptable for island hopping; verify with agent.",
            segments_involved=[7, 8],
        ),
        RuleResult(
            rule_id="R005",
            rule_name="Carrier Eligibility",
            passed=True,
            severity=Severity.VIOLATION,
            message="All carriers are oneworld members or affiliates.",
        ),
        RuleResult(
            rule_id="R006",
            rule_name="Surface Sector",
            passed=False,
            severity=Severity.INFO,
            message="JFK-MCO is a surface sector; passenger arranges own transport.",
            segments_involved=[11],
        ),
    ]
    return ValidationReport(itinerary=v3, results=results)


@pytest.fixture
def ntp_estimates() -> list[NTPEstimate]:
    """Create a list of NTP estimates for testing."""
    return [
        NTPEstimate(
            segment_index=0,
            route="CAI-AMM",
            carrier="RJ",
            distance_miles=450,
            method=NTPMethod.DISTANCE,
            rate=1.0,
            estimated_ntp=450,
            confidence="calculated",
            notes="Royal Jordanian distance-based",
        ),
        NTPEstimate(
            segment_index=1,
            route="AMM-DOH",
            carrier="QR",
            distance_miles=900,
            method=NTPMethod.DISTANCE,
            rate=1.0,
            estimated_ntp=900,
            confidence="calculated",
            notes="Qatar Airways distance-based",
        ),
        NTPEstimate(
            segment_index=2,
            route="DOH-NRT",
            carrier="QR",
            distance_miles=5200,
            method=NTPMethod.DISTANCE,
            rate=1.0,
            estimated_ntp=5200,
            confidence="calculated",
            notes="QSuite long-haul",
        ),
    ]


@pytest.fixture
def cost_estimate() -> CostEstimate:
    """Create a cost estimate for testing."""
    return CostEstimate(
        origin="CAI",
        ticket_type=TicketType.DONE4,
        base_fare_usd=7499.00,
        total_yq_usd=1850.00,
        total_per_person_usd=9349.00,
        total_all_pax_usd=18698.00,
        passengers=2,
        plating_carrier="AA",
        notes="Plated on AA for lowest YQ",
    )


@pytest.fixture
def segment_values() -> list[SegmentValue]:
    """Create segment value analysis data."""
    return [
        SegmentValue(
            segment_index=2,
            route="DOH-NRT",
            carrier="QR",
            estimated_j_cost_usd=6500,
            verdict="Excellent",
            suggestion="QSuite — top value segment",
            source="reference",
        ),
        SegmentValue(
            segment_index=10,
            route="SFO-JFK",
            carrier="AA",
            estimated_j_cost_usd=1200,
            verdict="Good",
            suggestion="A321T Flagship — solid domestic J",
            source="reference",
        ),
        SegmentValue(
            segment_index=7,
            route="NAN-FUN",
            carrier="FJ",
            estimated_j_cost_usd=300,
            verdict="Low",
            suggestion="ATR-72 single class — no J product",
            source="reference",
        ),
        SegmentValue(
            segment_index=14,
            route="MEX-MAD",
            carrier="IB",
            estimated_j_cost_usd=3200,
            verdict="Moderate",
            suggestion="Iberia A350 — decent long-haul J",
            source="reference",
        ),
    ]


@pytest.fixture
def booking_script(v3) -> BookingScript:
    """Generate a real booking script from the V3 itinerary."""
    gen = BookingGenerator()
    return gen.generate(v3)


# --- Formatter factory tests ---


class TestGetFormatter:
    """Test get_formatter factory function."""

    def test_rich(self):
        f = get_formatter("rich")
        assert isinstance(f, RichFormatter)

    def test_plain(self):
        f = get_formatter("plain")
        assert isinstance(f, PlainFormatter)

    def test_json(self):
        f = get_formatter("json")
        assert isinstance(f, JsonFormatter)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown formatter"):
            get_formatter("xml")


# --- RichFormatter tests ---


class TestRichFormatter:
    """Test RichFormatter produces rich output with expected content."""

    @pytest.fixture
    def fmt(self):
        return RichFormatter()

    def test_validation_non_empty(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        assert len(out) > 0

    def test_validation_contains_rule_names(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        assert "Origin Return" in out
        assert "Segment Limit" in out
        assert "Backtracking" in out

    def test_validation_contains_summary(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        assert "DONE4" in out
        assert "CAI" in out

    def test_validation_shows_pass_fail(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        assert "PASS" in out
        assert "FAIL" in out

    def test_validation_shows_fix_suggestion(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        assert "island hopping" in out

    def test_ntp_non_empty(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        assert len(out) > 0

    def test_ntp_contains_routes(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        assert "CAI-AMM" in out
        assert "DOH-NRT" in out

    def test_ntp_contains_total(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        assert "TOTAL" in out

    def test_ntp_contains_values(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        # Total NTP = 450 + 900 + 5200 = 6550
        assert "6,550" in out

    def test_cost_non_empty(self, fmt, cost_estimate):
        out = fmt.format_cost(cost_estimate)
        assert len(out) > 0

    def test_cost_contains_amounts(self, fmt, cost_estimate):
        out = fmt.format_cost(cost_estimate)
        assert "7,499.00" in out
        assert "18,698.00" in out

    def test_cost_contains_plating(self, fmt, cost_estimate):
        out = fmt.format_cost(cost_estimate)
        assert "AA" in out

    def test_value_non_empty(self, fmt, segment_values):
        out = fmt.format_value(segment_values)
        assert len(out) > 0

    def test_value_contains_verdicts(self, fmt, segment_values):
        out = fmt.format_value(segment_values)
        assert "Excellent" in out
        assert "Good" in out
        assert "Moderate" in out
        assert "Low" in out

    def test_value_contains_routes(self, fmt, segment_values):
        out = fmt.format_value(segment_values)
        assert "DOH-NRT" in out
        assert "SFO-JFK" in out

    def test_booking_non_empty(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        assert len(out) > 0

    def test_booking_contains_opening(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        assert "oneworld Explorer" in out

    def test_booking_contains_gds(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        assert "FQD" in out
        assert "ARNK" in out

    def test_booking_contains_warnings(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        assert "WARNING" in out or "Warnings" in out


# --- PlainFormatter tests ---


class TestPlainFormatter:
    """Test PlainFormatter produces clean text without ANSI escapes."""

    @pytest.fixture
    def fmt(self):
        return PlainFormatter()

    def _assert_no_ansi(self, text: str):
        """Assert no ANSI escape sequences in text."""
        # ANSI escapes start with ESC [ (0x1b 0x5b) or ESC ( or CSI
        ansi_pattern = re.compile(r"\x1b\[[\d;]*[a-zA-Z]|\x1b\(.|(\x9b)[\d;]*[a-zA-Z]")
        matches = ansi_pattern.findall(text)
        assert len(ansi_pattern.findall(text)) == 0, (
            f"Found ANSI escape sequences in plain text output: {matches}"
        )

    def test_validation_non_empty(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        assert len(out) > 0

    def test_validation_no_ansi(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        self._assert_no_ansi(out)

    def test_validation_contains_rule_names(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        assert "Origin Return" in out
        assert "Backtracking" in out

    def test_validation_contains_fix(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        assert "island hopping" in out

    def test_ntp_non_empty(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        assert len(out) > 0

    def test_ntp_no_ansi(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        self._assert_no_ansi(out)

    def test_ntp_contains_total(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        assert "TOTAL" in out

    def test_cost_non_empty(self, fmt, cost_estimate):
        out = fmt.format_cost(cost_estimate)
        assert len(out) > 0

    def test_cost_no_ansi(self, fmt, cost_estimate):
        out = fmt.format_cost(cost_estimate)
        self._assert_no_ansi(out)

    def test_cost_contains_amounts(self, fmt, cost_estimate):
        out = fmt.format_cost(cost_estimate)
        assert "7,499.00" in out

    def test_value_non_empty(self, fmt, segment_values):
        out = fmt.format_value(segment_values)
        assert len(out) > 0

    def test_value_no_ansi(self, fmt, segment_values):
        out = fmt.format_value(segment_values)
        self._assert_no_ansi(out)

    def test_value_contains_verdicts(self, fmt, segment_values):
        out = fmt.format_value(segment_values)
        assert "Excellent" in out
        assert "Low" in out

    def test_booking_non_empty(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        assert len(out) > 0

    def test_booking_no_ansi(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        self._assert_no_ansi(out)

    def test_booking_contains_opening(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        assert "oneworld Explorer" in out

    def test_booking_contains_gds(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        assert "FQD" in out


# --- JsonFormatter tests ---


class TestJsonFormatter:
    """Test JsonFormatter produces valid JSON with expected structure."""

    @pytest.fixture
    def fmt(self):
        return JsonFormatter()

    def test_validation_valid_json(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        data = json.loads(out)
        assert data["type"] == "validation_report"

    def test_validation_has_summary(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        data = json.loads(out)
        assert "summary" in data
        assert "violation_count" in data["summary"]
        assert "warning_count" in data["summary"]

    def test_validation_has_results(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        data = json.loads(out)
        assert "results" in data
        assert len(data["results"]) == 6

    def test_validation_result_fields(self, fmt, validation_report):
        out = fmt.format_validation(validation_report)
        data = json.loads(out)
        r = data["results"][0]
        assert "rule_id" in r
        assert "rule_name" in r
        assert "passed" in r
        assert "severity" in r
        assert "message" in r

    def test_ntp_valid_json(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        data = json.loads(out)
        assert data["type"] == "ntp_estimates"

    def test_ntp_has_summary(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        data = json.loads(out)
        assert data["summary"]["total_ntp"] == 6550.0
        assert data["summary"]["segment_count"] == 3

    def test_ntp_estimates_list(self, fmt, ntp_estimates):
        out = fmt.format_ntp(ntp_estimates)
        data = json.loads(out)
        assert len(data["estimates"]) == 3
        assert data["estimates"][0]["route"] == "CAI-AMM"

    def test_cost_valid_json(self, fmt, cost_estimate):
        out = fmt.format_cost(cost_estimate)
        data = json.loads(out)
        assert data["type"] == "cost_estimate"

    def test_cost_has_amounts(self, fmt, cost_estimate):
        out = fmt.format_cost(cost_estimate)
        data = json.loads(out)
        assert data["base_fare_usd"] == 7499.00
        assert data["total_all_pax_usd"] == 18698.00
        assert data["passengers"] == 2

    def test_value_valid_json(self, fmt, segment_values):
        out = fmt.format_value(segment_values)
        data = json.loads(out)
        assert data["type"] == "segment_value_analysis"

    def test_value_has_values(self, fmt, segment_values):
        out = fmt.format_value(segment_values)
        data = json.loads(out)
        assert data["segment_count"] == 4
        verdicts = [v["verdict"] for v in data["values"]]
        assert "Excellent" in verdicts
        assert "Low" in verdicts

    def test_booking_valid_json(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        data = json.loads(out)
        assert data["type"] == "booking_script"

    def test_booking_has_segments(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        data = json.loads(out)
        assert "segments" in data
        assert len(data["segments"]) == 16

    def test_booking_has_gds_commands(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        data = json.loads(out)
        assert "gds_commands" in data
        assert len(data["gds_commands"]) > 0

    def test_booking_has_warnings(self, fmt, booking_script):
        out = fmt.format_booking(booking_script)
        data = json.loads(out)
        assert "warnings" in data
        assert len(data["warnings"]) > 0


# --- Protocol conformance ---


class TestProtocolConformance:
    """Verify all formatters satisfy the Formatter protocol."""

    @pytest.mark.parametrize("name", ["rich", "plain", "json"])
    def test_all_methods_exist(self, name):
        """Each formatter has all required methods."""
        fmt = get_formatter(name)
        assert hasattr(fmt, "format_validation")
        assert hasattr(fmt, "format_ntp")
        assert hasattr(fmt, "format_cost")
        assert hasattr(fmt, "format_value")
        assert hasattr(fmt, "format_booking")

    @pytest.mark.parametrize("name", ["rich", "plain", "json"])
    def test_all_return_strings(
        self,
        name,
        validation_report,
        ntp_estimates,
        cost_estimate,
        segment_values,
        booking_script,
    ):
        """Each formatter returns strings from every method."""
        fmt = get_formatter(name)
        assert isinstance(fmt.format_validation(validation_report), str)
        assert isinstance(fmt.format_ntp(ntp_estimates), str)
        assert isinstance(fmt.format_cost(cost_estimate), str)
        assert isinstance(fmt.format_value(segment_values), str)
        assert isinstance(fmt.format_booking(booking_script), str)

    @pytest.mark.parametrize("name", ["rich", "plain", "json"])
    def test_all_non_empty(
        self,
        name,
        validation_report,
        ntp_estimates,
        cost_estimate,
        segment_values,
        booking_script,
    ):
        """Each formatter produces non-empty output."""
        fmt = get_formatter(name)
        assert len(fmt.format_validation(validation_report)) > 0
        assert len(fmt.format_ntp(ntp_estimates)) > 0
        assert len(fmt.format_cost(cost_estimate)) > 0
        assert len(fmt.format_value(segment_values)) > 0
        assert len(fmt.format_booking(booking_script)) > 0
