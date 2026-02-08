"""Property-based fuzz tests for the RTW Validator using Hypothesis.

These tests generate random itineraries and verify that the Validator
never crashes, always returns well-formed results, and exhibits
consistent invariant properties regardless of input.
"""

import pytest
from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st

from rtw.models import (
    CabinClass,
    Itinerary,
    RuleResult,
    Segment,
    SegmentType,
    Severity,
    Ticket,
    TicketType,
    ValidationReport,
)
from rtw.validator import Validator


# ---------------------------------------------------------------------------
# Real airport codes for mixing with random ones
# ---------------------------------------------------------------------------
REAL_AIRPORTS = [
    "CAI",
    "NRT",
    "SFO",
    "DOH",
    "HKG",
    "AMM",
    "LHR",
    "SYD",
    "JFK",
    "LAX",
    "CDG",
    "SIN",
    "BKK",
    "DEL",
    "DXB",
    "ICN",
    "TPE",
    "KUL",
    "MNL",
    "MEL",
    "AKL",
    "SCL",
    "GRU",
    "BOG",
    "EZE",
    "JNB",
    "ADD",
    "NBO",
    "CMB",
    "HND",
]

REAL_CARRIERS = [
    "BA",
    "QF",
    "AA",
    "CX",
    "JL",
    "MH",
    "QR",
    "RJ",
    "AY",
    "IB",
    "AS",
    "FJ",
    "AT",
    "UL",
    "S7",
]


# ---------------------------------------------------------------------------
# Custom Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def random_airport_code(draw):
    """Generate a 3-letter uppercase airport code.

    50% chance of using a real IATA code, 50% random 3-letter combo.
    """
    use_real = draw(st.booleans())
    if use_real:
        return draw(st.sampled_from(REAL_AIRPORTS))
    return draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=(), whitelist_characters="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            ),
            min_size=3,
            max_size=3,
        )
    )


@st.composite
def random_carrier_code(draw):
    """Generate a 2-letter uppercase carrier code or None.

    60% real carrier, 20% random 2-letter, 20% None.
    """
    choice = draw(st.integers(min_value=0, max_value=4))
    if choice <= 2:
        return draw(st.sampled_from(REAL_CARRIERS))
    elif choice == 3:
        return draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=(), whitelist_characters="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                ),
                min_size=2,
                max_size=2,
            )
        )
    else:
        return None


@st.composite
def random_segment(draw):
    """Generate a random Segment with from, to, carrier, and type."""
    from_airport = draw(random_airport_code())
    to_airport = draw(random_airport_code())
    carrier = draw(random_carrier_code())
    seg_type = draw(st.sampled_from(list(SegmentType)))

    return Segment(
        **{
            "from": from_airport,
            "to": to_airport,
            "carrier": carrier,
            "type": seg_type.value,
        }
    )


@st.composite
def random_itinerary(draw):
    """Generate a random Itinerary with a random ticket and 1-20 segments."""
    ticket_type = draw(st.sampled_from(list(TicketType)))
    cabin = draw(st.sampled_from(list(CabinClass)))
    origin = draw(random_airport_code())
    passengers = draw(st.integers(min_value=1, max_value=9))

    ticket = Ticket(
        type=ticket_type,
        cabin=cabin,
        origin=origin,
        passengers=passengers,
    )

    num_segments = draw(st.integers(min_value=1, max_value=20))
    segments = draw(st.lists(random_segment(), min_size=num_segments, max_size=num_segments))

    return Itinerary(ticket=ticket, segments=segments)


# ---------------------------------------------------------------------------
# Shared validator instance (stateless, safe to reuse)
# ---------------------------------------------------------------------------
_validator = Validator()


# ---------------------------------------------------------------------------
# Test: Validator never crashes
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestValidatorNeverCrashes:
    """The Validator must never raise an exception for ANY input.

    Even garbage itineraries with random airports and carriers should
    produce a ValidationReport (with violations), never an exception.
    """

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_validate_never_raises(self, itinerary: Itinerary):
        """validate() returns a ValidationReport for any random itinerary."""
        report = _validator.validate(itinerary)

        # Must return a ValidationReport, never None
        assert isinstance(report, ValidationReport)

        # Must contain the original itinerary
        assert report.itinerary is itinerary

        # Results must be a list (possibly empty, but should have rules)
        assert isinstance(report.results, list)


# ---------------------------------------------------------------------------
# Test: Rule result consistency
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestRuleResultConsistency:
    """Every ValidationReport must have internally consistent results."""

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_all_results_are_rule_results(self, itinerary: Itinerary):
        """Every item in results is a RuleResult instance."""
        report = _validator.validate(itinerary)

        for result in report.results:
            assert isinstance(result, RuleResult), f"Expected RuleResult, got {type(result)}"

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_each_result_has_rule_id_and_message(self, itinerary: Itinerary):
        """Every RuleResult has a non-empty rule_id and message."""
        report = _validator.validate(itinerary)

        for result in report.results:
            assert isinstance(result.rule_id, str) and len(result.rule_id) > 0, (
                f"Empty or non-string rule_id: {result.rule_id!r}"
            )
            assert isinstance(result.message, str) and len(result.message) > 0, (
                f"Empty or non-string message for rule {result.rule_id}: {result.message!r}"
            )

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_passed_matches_no_violations(self, itinerary: Itinerary):
        """report.passed == True iff there are no VIOLATION-severity failures."""
        report = _validator.validate(itinerary)

        has_violations = any(
            not r.passed and r.severity == Severity.VIOLATION for r in report.results
        )
        assert report.passed == (not has_violations), (
            f"passed={report.passed} but has_violations={has_violations}, "
            f"violation_count={report.violation_count}"
        )

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_violation_warning_counts_consistent(self, itinerary: Itinerary):
        """violation_count + warning_count <= total results."""
        report = _validator.validate(itinerary)

        assert report.violation_count + report.warning_count <= len(report.results), (
            f"violation_count={report.violation_count} + warning_count={report.warning_count} "
            f"> total results={len(report.results)}"
        )


# ---------------------------------------------------------------------------
# Test: Invariant properties
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestInvariantProperties:
    """Structural invariants that must hold for all inputs."""

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_validation_is_deterministic(self, itinerary: Itinerary):
        """Running validate twice on the same input produces identical results."""
        report1 = _validator.validate(itinerary)
        report2 = _validator.validate(itinerary)

        assert len(report1.results) == len(report2.results), (
            f"Non-deterministic: {len(report1.results)} vs {len(report2.results)} results"
        )
        assert report1.violation_count == report2.violation_count
        assert report1.warning_count == report2.warning_count
        assert report1.passed == report2.passed

        # Check result-by-result consistency
        for r1, r2 in zip(report1.results, report2.results):
            assert r1.rule_id == r2.rule_id, (
                f"Non-deterministic rule ordering: {r1.rule_id} vs {r2.rule_id}"
            )
            assert r1.passed == r2.passed, (
                f"Non-deterministic pass/fail for {r1.rule_id}: {r1.passed} vs {r2.passed}"
            )

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_at_least_one_rule_result(self, itinerary: Itinerary):
        """Every validation produces at least one rule result."""
        report = _validator.validate(itinerary)

        assert len(report.results) >= 1, (
            "Validation produced zero results — at least one rule should always fire"
        )

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_all_rule_ids_are_nonempty_strings(self, itinerary: Itinerary):
        """Every rule_id in the results is a non-empty string."""
        report = _validator.validate(itinerary)

        for result in report.results:
            assert isinstance(result.rule_id, str), (
                f"rule_id is not a string: {type(result.rule_id)}"
            )
            assert len(result.rule_id) > 0, "rule_id is empty"

    @given(itinerary=random_itinerary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_all_severities_are_valid(self, itinerary: Itinerary):
        """Every result severity is one of the defined Severity enum values."""
        report = _validator.validate(itinerary)

        valid_severities = {Severity.VIOLATION, Severity.WARNING, Severity.INFO}
        for result in report.results:
            assert result.severity in valid_severities, (
                f"Invalid severity {result.severity!r} for rule {result.rule_id}"
            )
