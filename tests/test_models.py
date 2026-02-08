"""Tests for RTW domain models."""

import pytest
from pydantic import ValidationError

from rtw.models import (
    TicketType,
    SegmentType,
    Continent,
    TariffConference,
    NTPMethod,
    Severity,
    CONTINENT_TO_TC,
    Ticket,
    Segment,
    Itinerary,
    RuleResult,
    ValidationReport,
    NTPEstimate,
    CostEstimate,
    SegmentValue,
)


# --- Ticket Tests ---


class TestTicket:
    def test_origin_uppercase(self):
        t = Ticket(type="DONE4", cabin="business", origin="cai")
        assert t.origin == "CAI"

    def test_invalid_origin_length(self):
        with pytest.raises(ValidationError):
            Ticket(type="DONE4", cabin="business", origin="CA")

    def test_invalid_origin_too_long(self):
        with pytest.raises(ValidationError):
            Ticket(type="DONE4", cabin="business", origin="CAIR")

    def test_passengers_range(self):
        t = Ticket(type="DONE4", cabin="business", origin="CAI", passengers=9)
        assert t.passengers == 9
        with pytest.raises(ValidationError):
            Ticket(type="DONE4", cabin="business", origin="CAI", passengers=0)
        with pytest.raises(ValidationError):
            Ticket(type="DONE4", cabin="business", origin="CAI", passengers=10)

    def test_num_continents(self):
        assert Ticket(type="DONE3", cabin="business", origin="CAI").num_continents == 3
        assert Ticket(type="DONE4", cabin="business", origin="CAI").num_continents == 4
        assert Ticket(type="DONE5", cabin="business", origin="CAI").num_continents == 5
        assert Ticket(type="DONE6", cabin="business", origin="CAI").num_continents == 6

    def test_fare_prefix(self):
        assert Ticket(type="DONE4", cabin="business", origin="CAI").fare_prefix == "D"
        assert Ticket(type="LONE4", cabin="economy", origin="CAI").fare_prefix == "L"
        assert Ticket(type="AONE4", cabin="first", origin="CAI").fare_prefix == "A"

    def test_plating_carrier_uppercase(self):
        t = Ticket(type="DONE4", cabin="business", origin="CAI", plating_carrier="aa")
        assert t.plating_carrier == "AA"


# --- Segment Tests ---


class TestSegment:
    def test_from_alias(self):
        s = Segment(**{"from": "CAI", "to": "AMM", "carrier": "RJ"})
        assert s.from_airport == "CAI"
        assert s.to_airport == "AMM"

    def test_carrier_uppercase(self):
        s = Segment(**{"from": "CAI", "to": "AMM", "carrier": "rj"})
        assert s.carrier == "RJ"

    def test_airports_uppercase(self):
        s = Segment(**{"from": "cai", "to": "amm"})
        assert s.from_airport == "CAI"
        assert s.to_airport == "AMM"

    def test_surface_properties(self):
        s = Segment(**{"from": "JFK", "to": "MCO", "type": "surface"})
        assert s.is_surface is True
        assert s.is_flown is False
        assert s.is_stopover is False

    def test_stopover_properties(self):
        s = Segment(**{"from": "CAI", "to": "AMM", "carrier": "RJ", "type": "stopover"})
        assert s.is_stopover is True
        assert s.is_flown is True
        assert s.is_surface is False

    def test_transit_properties(self):
        s = Segment(**{"from": "HKG", "to": "SIN", "carrier": "CX", "type": "transit"})
        assert s.is_stopover is False
        assert s.is_flown is True

    def test_default_type_is_stopover(self):
        s = Segment(**{"from": "CAI", "to": "AMM"})
        assert s.type == SegmentType.STOPOVER


# --- Itinerary Tests ---


class TestItinerary:
    def test_min_one_segment(self):
        t = Ticket(type="DONE4", cabin="business", origin="CAI")
        s = Segment(**{"from": "CAI", "to": "AMM", "carrier": "RJ"})
        itin = Itinerary(ticket=t, segments=[s])
        assert len(itin.segments) == 1

    def test_empty_segments_rejected(self):
        t = Ticket(type="DONE4", cabin="business", origin="CAI")
        with pytest.raises(ValidationError):
            Itinerary(ticket=t, segments=[])

    def test_flown_segments_excludes_surface(self):
        t = Ticket(type="DONE4", cabin="business", origin="CAI")
        segments = [
            Segment(**{"from": "CAI", "to": "AMM", "carrier": "RJ", "type": "stopover"}),
            Segment(**{"from": "JFK", "to": "MCO", "type": "surface"}),
            Segment(**{"from": "MCO", "to": "MIA", "carrier": "AA", "type": "transit"}),
        ]
        itin = Itinerary(ticket=t, segments=segments)
        assert len(itin.segments) == 3
        assert len(itin.flown_segments) == 2
        assert len(itin.surface_segments) == 1
        assert len(itin.stopovers) == 1

    def test_v3_fixture_loads(self, v3_itinerary):
        """Test that the V3 fixture YAML can be parsed into models."""
        itin = Itinerary(**v3_itinerary)
        assert itin.ticket.type == TicketType.DONE4
        assert itin.ticket.origin == "CAI"
        assert len(itin.segments) == 16
        assert len(itin.surface_segments) == 1
        assert len(itin.flown_segments) == 15


# --- Enum Tests ---


class TestEnums:
    def test_ticket_type_values(self):
        assert TicketType.DONE4.value == "DONE4"
        assert TicketType.LONE5.value == "LONE5"

    def test_continent_to_tc(self):
        assert CONTINENT_TO_TC[Continent.EU_ME] == TariffConference.TC2
        assert CONTINENT_TO_TC[Continent.ASIA] == TariffConference.TC3
        assert CONTINENT_TO_TC[Continent.N_AMERICA] == TariffConference.TC1


# --- Result Model Tests ---


class TestResults:
    def test_rule_result_construction(self):
        r = RuleResult(
            rule_id="segment_count",
            rule_name="Segment Count",
            passed=True,
            message="OK",
        )
        assert r.passed is True
        assert r.severity == Severity.VIOLATION

    def test_validation_report_passed(self):
        t = Ticket(type="DONE4", cabin="business", origin="CAI")
        s = Segment(**{"from": "CAI", "to": "AMM", "carrier": "RJ"})
        itin = Itinerary(ticket=t, segments=[s])
        report = ValidationReport(
            itinerary=itin,
            results=[
                RuleResult(rule_id="r1", rule_name="R1", passed=True, message="OK"),
                RuleResult(rule_id="r2", rule_name="R2", passed=True, message="OK"),
            ],
        )
        assert report.passed is True
        assert report.violation_count == 0

    def test_validation_report_failed(self):
        t = Ticket(type="DONE4", cabin="business", origin="CAI")
        s = Segment(**{"from": "CAI", "to": "AMM", "carrier": "RJ"})
        itin = Itinerary(ticket=t, segments=[s])
        report = ValidationReport(
            itinerary=itin,
            results=[
                RuleResult(rule_id="r1", rule_name="R1", passed=True, message="OK"),
                RuleResult(
                    rule_id="r2",
                    rule_name="R2",
                    passed=False,
                    message="Failed",
                    severity=Severity.VIOLATION,
                ),
            ],
        )
        assert report.passed is False
        assert report.violation_count == 1

    def test_warning_does_not_fail_report(self):
        t = Ticket(type="DONE4", cabin="business", origin="CAI")
        s = Segment(**{"from": "CAI", "to": "AMM", "carrier": "RJ"})
        itin = Itinerary(ticket=t, segments=[s])
        report = ValidationReport(
            itinerary=itin,
            results=[
                RuleResult(rule_id="r1", rule_name="R1", passed=True, message="OK"),
                RuleResult(
                    rule_id="r2",
                    rule_name="R2",
                    passed=False,
                    message="Warn",
                    severity=Severity.WARNING,
                ),
            ],
        )
        assert report.passed is True  # Warnings don't cause failure
        assert report.warning_count == 1

    def test_ntp_estimate(self):
        n = NTPEstimate(
            segment_index=0,
            route="DOH-NRT",
            carrier="QR",
            distance_miles=5183,
            method=NTPMethod.DISTANCE,
            rate=50,
            estimated_ntp=2592,
            confidence="calculated",
        )
        assert n.estimated_ntp == 2592

    def test_cost_estimate(self):
        c = CostEstimate(
            origin="CAI",
            ticket_type=TicketType.DONE4,
            base_fare_usd=4000,
            total_yq_usd=1800,
            total_per_person_usd=5800,
            total_all_pax_usd=11600,
            passengers=2,
            plating_carrier="AA",
        )
        assert c.total_all_pax_usd == 11600

    def test_segment_value(self):
        sv = SegmentValue(
            segment_index=2,
            route="DOH-NRT",
            carrier="QR",
            estimated_j_cost_usd=3000,
            verdict="Excellent",
        )
        assert sv.verdict == "Excellent"
