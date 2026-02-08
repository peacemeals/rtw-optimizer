"""Integration tests for the RTW Validator — runs ALL rules against fixtures."""

import pytest

from rtw.models import (
    Itinerary,
    Ticket,
    Segment,
    Severity,
    ValidationReport,
    RuleResult,
)
from rtw.validator import Validator, build_context
from rtw.rules.base import get_registered_rules


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_itinerary(raw: dict) -> Itinerary:
    """Build an Itinerary model from raw YAML dict."""
    return Itinerary(**raw)


def _make_minimal_valid_itinerary() -> Itinerary:
    """A clearly INVALID itinerary for negative-testing (too few segments, etc.)."""
    return Itinerary(
        ticket=Ticket(type="DONE4", cabin="business", origin="CAI"),
        segments=[
            Segment(**{"from": "CAI", "to": "LHR", "carrier": "BA", "type": "stopover"}),
            Segment(**{"from": "LHR", "to": "CAI", "carrier": "BA", "type": "final"}),
        ],
    )


def _make_bad_direction_itinerary() -> Itinerary:
    """An itinerary that backtracks (TC reversal) to trigger direction violation."""
    return Itinerary(
        ticket=Ticket(type="DONE4", cabin="business", origin="LHR"),
        segments=[
            # LHR -> NRT (TC2 -> TC3)
            Segment(**{"from": "LHR", "to": "NRT", "carrier": "BA", "type": "stopover"}),
            # NRT -> SYD (TC3 -> TC3, within zone)
            Segment(**{"from": "NRT", "to": "SYD", "carrier": "QF", "type": "stopover"}),
            # SYD -> SFO (TC3 -> TC1)
            Segment(**{"from": "SYD", "to": "SFO", "carrier": "QF", "type": "stopover"}),
            # SFO -> NRT (TC1 -> TC3) — REVERSAL!
            Segment(**{"from": "SFO", "to": "NRT", "carrier": "AA", "type": "stopover"}),
            # NRT -> LHR (TC3 -> TC2)
            Segment(**{"from": "NRT", "to": "LHR", "carrier": "BA", "type": "final"}),
        ],
    )


# ---------------------------------------------------------------------------
# Test: rule discovery
# ---------------------------------------------------------------------------


class TestRuleDiscovery:
    """Verify rule auto-discovery picks up all registered rules."""

    def test_all_rules_registered(self):
        """Validator imports trigger registration of all rule classes."""
        Validator()  # triggers rule registration via imports
        rules = get_registered_rules()
        # We expect at least 15 rules across all modules
        assert len(rules) >= 15, (
            f"Expected >=15 registered rules, got {len(rules)}: "
            f"{[r.rule_id for r in (r() for r in rules)]}"
        )

    def test_each_rule_has_required_attrs(self):
        """Every registered rule class must have rule_id, rule_name, rule_reference."""
        Validator()  # triggers rule registration via imports
        for rule_cls in get_registered_rules():
            rule = rule_cls()
            assert hasattr(rule, "rule_id"), f"{rule_cls.__name__} missing rule_id"
            assert hasattr(rule, "rule_name"), f"{rule_cls.__name__} missing rule_name"
            assert hasattr(rule, "rule_reference"), f"{rule_cls.__name__} missing rule_reference"
            assert callable(getattr(rule, "check", None)), f"{rule_cls.__name__} missing check()"

    def test_no_duplicate_rule_ids(self):
        """No two rules should share the same rule_id."""
        Validator()  # triggers rule registration via imports
        ids = [r().rule_id for r in get_registered_rules()]
        assert len(ids) == len(set(ids)), (
            f"Duplicate rule_ids: {[x for x in ids if ids.count(x) > 1]}"
        )


# ---------------------------------------------------------------------------
# Test: V3 fixture passes all rules
# ---------------------------------------------------------------------------


class TestV3Integration:
    """The V3 reference routing must pass all rules (no violations)."""

    def test_v3_passes_validation(self, v3_itinerary):
        """V3 fixture should produce zero violations."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        violations = report.violations
        if violations:
            details = "\n".join(f"  [{v.rule_id}] {v.message}" for v in violations)
            pytest.fail(f"V3 fixture has {len(violations)} violation(s):\n{details}")

        assert report.passed is True

    def test_v3_has_warnings_only(self, v3_itinerary):
        """V3 may have warnings (e.g., origin continent stopovers) but no violations."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        assert report.violation_count == 0
        # V3 should produce at least 1 warning (origin continent stopovers)
        assert report.warning_count >= 1

    def test_v3_segment_count(self, v3_itinerary):
        """V3 has 16 segments — at the maximum allowed."""
        itin = _build_itinerary(v3_itinerary)
        assert len(itin.segments) == 16

    def test_v3_context_build(self, v3_itinerary):
        """build_context produces correct data for V3."""
        itin = _build_itinerary(v3_itinerary)
        ctx = build_context(itin)

        # Origin is CAI = EU_ME
        from rtw.models import Continent, TariffConference

        assert ctx.origin_continent == Continent.EU_ME
        assert ctx.origin_tc == TariffConference.TC2

        # Should visit 4 continents for DONE4
        assert len(ctx.continents_visited) == 4

        # Should have same-city pairs (NRT/HND, TSA/TPE)
        assert len(ctx.same_city_pairs) == 2

    def test_v3_all_rule_ids_present(self, v3_itinerary):
        """Every registered rule should produce at least one result."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        result_rule_ids = {r.rule_id for r in report.results}
        registered_rule_ids = {r().rule_id for r in get_registered_rules()}

        missing = registered_rule_ids - result_rule_ids
        assert not missing, f"Rules produced no results: {missing}"


# ---------------------------------------------------------------------------
# Test: clearly invalid itinerary
# ---------------------------------------------------------------------------


class TestInvalidItinerary:
    """An invalid itinerary should trigger specific violations."""

    def test_too_few_segments(self):
        """Only 2 segments — must violate segment_count."""
        itin = _make_minimal_valid_itinerary()
        validator = Validator()
        report = validator.validate(itin)

        assert report.passed is False
        violation_ids = {v.rule_id for v in report.violations}
        assert "segment_count" in violation_ids

    def test_missing_ocean_crossings(self):
        """LHR->CAI has no Pacific/Atlantic ocean crossing."""
        itin = _make_minimal_valid_itinerary()
        validator = Validator()
        report = validator.validate(itin)

        violation_ids = {v.rule_id for v in report.violations}
        assert "ocean_crossings" in violation_ids

    def test_direction_reversal(self):
        """Backtracking itinerary should trigger direction_of_travel violation."""
        itin = _make_bad_direction_itinerary()
        validator = Validator()
        report = validator.validate(itin)

        violation_ids = {v.rule_id for v in report.violations}
        assert "direction_of_travel" in violation_ids, (
            f"Expected direction_of_travel violation, got: {violation_ids}"
        )


# ---------------------------------------------------------------------------
# Test: full validate() flow
# ---------------------------------------------------------------------------


class TestValidateFlow:
    """End-to-end validate() returns a well-formed ValidationReport."""

    def test_report_structure(self, v3_itinerary):
        """validate() returns a ValidationReport with itinerary and results."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        assert isinstance(report, ValidationReport)
        assert report.itinerary is itin
        assert len(report.results) > 0

    def test_all_results_are_rule_results(self, v3_itinerary):
        """Every result is a RuleResult with correct fields."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        for r in report.results:
            assert isinstance(r, RuleResult)
            assert isinstance(r.rule_id, str) and len(r.rule_id) > 0
            assert isinstance(r.rule_name, str) and len(r.rule_name) > 0
            assert isinstance(r.passed, bool)
            assert isinstance(r.message, str) and len(r.message) > 0
            assert r.severity in (Severity.VIOLATION, Severity.WARNING, Severity.INFO)

    def test_validate_idempotent(self, v3_itinerary):
        """Running validate twice produces same result counts."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report1 = validator.validate(itin)
        report2 = validator.validate(itin)

        assert report1.violation_count == report2.violation_count
        assert report1.warning_count == report2.warning_count
        assert len(report1.results) == len(report2.results)

    def test_34000nm_cap_not_enforced(self, v3_itinerary):
        """Verify there is NO distance cap rule — oneworld Explorer has no 34,000nm limit."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        # No rule should reference a distance/mileage cap
        for r in report.results:
            assert "34,000" not in r.message, f"Rule {r.rule_id} mentions 34,000nm cap"
            assert "34000" not in r.message, f"Rule {r.rule_id} mentions 34000nm cap"
            assert "mileage cap" not in r.message.lower(), f"Rule {r.rule_id} mentions mileage cap"

        # No registered rule should have "distance_cap" or "mileage" in its rule_id
        all_ids = {r().rule_id for r in get_registered_rules()}
        assert "distance_cap" not in all_ids
        assert "mileage_cap" not in all_ids


# ---------------------------------------------------------------------------
# Test: hemisphere revisit rule specifically
# ---------------------------------------------------------------------------


class TestHemisphereRevisit:
    """Direct tests for the HemisphereRevisitRule."""

    def test_v3_no_continent_revisit(self, v3_itinerary):
        """V3 only revisits origin continent (EU_ME) for the return — should pass."""
        itin = _build_itinerary(v3_itinerary)
        ctx = build_context(itin)

        from rtw.rules.hemisphere import HemisphereRevisitRule

        rule = HemisphereRevisitRule()
        results = rule.check(itin, ctx)

        assert all(r.passed for r in results), (
            f"HemisphereRevisitRule failed: {[r.message for r in results if not r.passed]}"
        )

    def test_northern_hemisphere_two_visits_pass(self):
        """Asia visited twice in a westbound routing should PASS (northern hemisphere allows 2).

        Routing: SYD -> HKG -> LHR -> JFK -> NRT -> SYD (westbound)
        Transitions: SWP -> Asia -> EU_ME -> N_America -> Asia -> SWP
        Asia visits: 2 (northern hemisphere, max 2). PASS.
        SWP visits: 2 (origin + return). Effective max = 1 + 1 = 2. PASS.
        """
        from rtw.rules.hemisphere import HemisphereRevisitRule

        itin = Itinerary(
            ticket=Ticket(type="DONE4", cabin="business", origin="SYD"),
            segments=[
                Segment(**{"from": "SYD", "to": "HKG", "carrier": "CX", "type": "stopover"}),
                Segment(**{"from": "HKG", "to": "LHR", "carrier": "CX", "type": "stopover"}),
                Segment(**{"from": "LHR", "to": "JFK", "carrier": "BA", "type": "stopover"}),
                Segment(**{"from": "JFK", "to": "NRT", "carrier": "JL", "type": "stopover"}),
                Segment(**{"from": "NRT", "to": "SYD", "carrier": "QF", "type": "final"}),
            ],
        )
        ctx = build_context(itin)
        rule = HemisphereRevisitRule()
        results = rule.check(itin, ctx)

        assert all(r.passed for r in results), (
            f"Expected PASS for northern hemisphere 2-visit but got failures: "
            f"{[r.message for r in results if not r.passed]}"
        )
        # Verify INFO message about Asia 2/2
        assert any("Asia" in r.message and "2" in r.message for r in results)

    def test_southern_hemisphere_revisit_fails(self):
        """SWP visited twice (non-origin) should FAIL (southern hemisphere max 1).

        Routing: LHR -> SYD -> HKG -> SYD -> SFO -> LHR (eastbound)
        Transitions: EU_ME -> SWP -> Asia -> SWP -> N_America -> EU_ME
        SWP visits: 2 (southern hemisphere, max 1). VIOLATION.
        """
        from rtw.rules.hemisphere import HemisphereRevisitRule

        itin = Itinerary(
            ticket=Ticket(type="DONE4", cabin="business", origin="LHR"),
            segments=[
                Segment(**{"from": "LHR", "to": "SYD", "carrier": "QF", "type": "stopover"}),
                Segment(**{"from": "SYD", "to": "HKG", "carrier": "CX", "type": "stopover"}),
                Segment(**{"from": "HKG", "to": "SYD", "carrier": "CX", "type": "stopover"}),
                Segment(**{"from": "SYD", "to": "SFO", "carrier": "QF", "type": "stopover"}),
                Segment(**{"from": "SFO", "to": "LHR", "carrier": "BA", "type": "final"}),
            ],
        )
        ctx = build_context(itin)
        rule = HemisphereRevisitRule()
        results = rule.check(itin, ctx)

        assert any(not r.passed for r in results), (
            f"Expected SWP revisit violation but all passed: {[r.message for r in results]}"
        )
        assert any("SWP" in r.message for r in results if not r.passed)

    def test_northern_three_visits_fails(self):
        """Asia visited 3 times should FAIL (northern hemisphere max 2).

        Routing: LHR -> NRT -> SYD -> HKG -> NAN -> BKK -> SFO -> LHR (eastbound)
        Transitions: EU_ME -> Asia -> SWP -> Asia -> SWP -> Asia -> N_America -> EU_ME
        Asia visits: 3 (max 2). VIOLATION.
        """
        from rtw.rules.hemisphere import HemisphereRevisitRule

        itin = Itinerary(
            ticket=Ticket(type="DONE5", cabin="business", origin="LHR"),
            segments=[
                Segment(**{"from": "LHR", "to": "NRT", "carrier": "BA", "type": "stopover"}),
                Segment(**{"from": "NRT", "to": "SYD", "carrier": "QF", "type": "stopover"}),
                Segment(**{"from": "SYD", "to": "HKG", "carrier": "CX", "type": "stopover"}),
                Segment(**{"from": "HKG", "to": "NAN", "carrier": "FJ", "type": "stopover"}),
                Segment(**{"from": "NAN", "to": "BKK", "carrier": "FJ", "type": "stopover"}),
                Segment(**{"from": "BKK", "to": "SFO", "carrier": "CX", "type": "stopover"}),
                Segment(**{"from": "SFO", "to": "LHR", "carrier": "BA", "type": "final"}),
            ],
        )
        ctx = build_context(itin)
        rule = HemisphereRevisitRule()
        results = rule.check(itin, ctx)

        assert any(not r.passed for r in results), (
            f"Expected Asia 3-visit violation but all passed: {[r.message for r in results]}"
        )
        assert any("Asia" in r.message and "3" in r.message for r in results if not r.passed)

    def test_southern_origin_return_allowed(self):
        """Southern hemisphere origin (SYD/SWP) can return home without violation.

        Routing: SYD -> NRT -> LAX -> LHR -> SYD (eastbound)
        Transitions: SWP -> Asia -> N_America -> EU_ME -> SWP
        SWP visits: 2 (origin + return). Effective max = 1 + 1 = 2. PASS.
        """
        from rtw.rules.hemisphere import HemisphereRevisitRule

        itin = Itinerary(
            ticket=Ticket(type="DONE4", cabin="business", origin="SYD"),
            segments=[
                Segment(**{"from": "SYD", "to": "NRT", "carrier": "JL", "type": "stopover"}),
                Segment(**{"from": "NRT", "to": "LAX", "carrier": "JL", "type": "stopover"}),
                Segment(**{"from": "LAX", "to": "LHR", "carrier": "BA", "type": "stopover"}),
                Segment(**{"from": "LHR", "to": "SYD", "carrier": "QF", "type": "final"}),
            ],
        )
        ctx = build_context(itin)
        rule = HemisphereRevisitRule()
        results = rule.check(itin, ctx)

        assert all(r.passed for r in results), (
            f"Expected PASS for southern origin return but got failures: "
            f"{[r.message for r in results if not r.passed]}"
        )

    def test_asia_swp_europe_bridge_info(self):
        """When Asia is visited 2x with SWP+EU_ME present, INFO should mention bridge exception.

        Same routing as test_northern_hemisphere_two_visits_pass:
        SYD -> HKG -> LHR -> JFK -> NRT -> SYD
        Both SWP and EU_ME appear in transitions -> bridge exception applies.
        """
        from rtw.rules.hemisphere import HemisphereRevisitRule

        itin = Itinerary(
            ticket=Ticket(type="DONE4", cabin="business", origin="SYD"),
            segments=[
                Segment(**{"from": "SYD", "to": "HKG", "carrier": "CX", "type": "stopover"}),
                Segment(**{"from": "HKG", "to": "LHR", "carrier": "CX", "type": "stopover"}),
                Segment(**{"from": "LHR", "to": "JFK", "carrier": "BA", "type": "stopover"}),
                Segment(**{"from": "JFK", "to": "NRT", "carrier": "JL", "type": "stopover"}),
                Segment(**{"from": "NRT", "to": "SYD", "carrier": "QF", "type": "final"}),
            ],
        )
        ctx = build_context(itin)
        rule = HemisphereRevisitRule()
        results = rule.check(itin, ctx)

        assert all(r.passed for r in results)
        # Check for SWP-Europe bridge exception mention
        assert any(
            "SWP-Europe" in r.message or "bridge" in r.message.lower()
            for r in results
        ), f"Expected SWP-Europe bridge info in messages: {[r.message for r in results]}"
