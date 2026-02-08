"""Comprehensive V3 routing integration tests — T045.

Tests the full analysis pipeline (validate -> cost -> ntp -> value -> booking)
against the V3 reference routing fixture, with detailed rule-by-rule checks,
geography verification, a clean itinerary variant, and mileage cap negation.
"""

import pytest

from rtw.models import (
    Itinerary,
    Ticket,
    Segment,
    Severity,
    RuleResult,
    CostEstimate,
    NTPEstimate,
    SegmentValue,
    Continent,
    TariffConference,
    CONTINENT_TO_TC,
)
from rtw.validator import Validator, build_context
from rtw.cost import CostEstimator
from rtw.ntp import NTPCalculator
from rtw.value import SegmentValueAnalyzer
from rtw.booking import BookingGenerator, BookingScript
from rtw.continents import get_continent
from rtw.rules.base import get_registered_rules


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_itinerary(raw: dict) -> Itinerary:
    """Build an Itinerary model from raw YAML dict."""
    return Itinerary(**raw)


def _make_clean_itinerary() -> Itinerary:
    """Build a simpler itinerary that passes ALL rules with 0 warnings.

    This is a DONE4 business itinerary from LHR that visits 4 continents
    (EU_ME, Asia, SWP, N_America) with only 2 stopovers in origin continent
    (EU_ME), so no origin_continent_stopovers warning is generated.

    Route: LHR -> NRT -> SYD -> SFO -> LHR (eastbound)
    TC sequence: TC2 -> TC3 -> TC3 -> TC1 -> TC2
    """
    return Itinerary(
        ticket=Ticket(type="DONE4", cabin="business", origin="LHR"),
        segments=[
            # EU_ME -> Asia (TC2 -> TC3)
            Segment(
                **{
                    "from": "LHR",
                    "to": "NRT",
                    "carrier": "BA",
                    "date": "2026-04-01",
                    "type": "stopover",
                }
            ),
            # Asia -> SWP (within TC3)
            Segment(
                **{
                    "from": "NRT",
                    "to": "SYD",
                    "carrier": "QF",
                    "date": "2026-04-05",
                    "type": "stopover",
                }
            ),
            # SWP -> N_America (TC3 -> TC1 — Pacific crossing)
            Segment(
                **{
                    "from": "SYD",
                    "to": "LAX",
                    "carrier": "QF",
                    "date": "2026-04-10",
                    "type": "stopover",
                }
            ),
            # N_America internal
            Segment(
                **{
                    "from": "LAX",
                    "to": "JFK",
                    "carrier": "AA",
                    "date": "2026-04-14",
                    "type": "stopover",
                }
            ),
            # N_America -> EU_ME (TC1 -> TC2 — Atlantic crossing)
            Segment(
                **{
                    "from": "JFK",
                    "to": "LHR",
                    "carrier": "BA",
                    "date": "2026-04-18",
                    "type": "final",
                }
            ),
        ],
    )


# ---------------------------------------------------------------------------
# TestV3FullPipeline — Complete analysis pipeline
# ---------------------------------------------------------------------------


class TestV3FullPipeline:
    """Test the complete analysis pipeline: validate -> cost -> ntp -> value -> booking."""

    def test_validate_passes(self, v3_itinerary):
        """V3 fixture passes validation with 0 violations."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        assert report.passed is True, (
            f"Expected PASS, got {report.violation_count} violations: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in report.violations)
        )
        assert report.violation_count == 0

    def test_cost_returns_estimate(self, v3_itinerary):
        """CostEstimator.estimate_total returns a CostEstimate with reasonable values."""
        itin = _build_itinerary(v3_itinerary)
        estimator = CostEstimator()
        cost = estimator.estimate_total(itin, plating_carrier="AA")

        assert isinstance(cost, CostEstimate)
        assert cost.origin == "CAI"
        assert cost.passengers == 2
        # Base fare should be positive
        assert cost.base_fare_usd > 0, f"Base fare should be > 0, got {cost.base_fare_usd}"
        # Total per person should include fare + YQ
        assert cost.total_per_person_usd >= cost.base_fare_usd
        # Total all pax = per_person * 2
        assert cost.total_all_pax_usd == cost.total_per_person_usd * cost.passengers
        # YQ should be non-negative
        assert cost.total_yq_usd >= 0
        # Plating carrier
        assert cost.plating_carrier == "AA"

    def test_ntp_returns_estimates(self, v3_itinerary):
        """NTPCalculator.calculate returns a list of NTPEstimate with total in reasonable range."""
        itin = _build_itinerary(v3_itinerary)
        calc = NTPCalculator()
        ntp_list = calc.calculate(itin)

        assert isinstance(ntp_list, list)
        assert len(ntp_list) == 16, f"Expected 16 NTP estimates, got {len(ntp_list)}"
        for est in ntp_list:
            assert isinstance(est, NTPEstimate)
            assert est.estimated_ntp >= 0

        # Total NTP should be positive (a round-the-world trip earns significant NTP)
        total_ntp = sum(e.estimated_ntp for e in ntp_list)
        assert total_ntp > 0, f"Total NTP should be > 0, got {total_ntp}"

        # Surface sector should earn 0 NTP
        surface_est = [e for e in ntp_list if "SURFACE" in e.carrier or e.distance_miles == 0]
        for s in surface_est:
            assert s.estimated_ntp == 0, f"Surface sector NTP should be 0, got {s.estimated_ntp}"

    def test_value_returns_analysis(self, v3_itinerary):
        """SegmentValueAnalyzer.analyze returns correct number of SegmentValue entries."""
        itin = _build_itinerary(v3_itinerary)
        analyzer = SegmentValueAnalyzer()
        values = analyzer.analyze(itin)

        assert isinstance(values, list)
        assert len(values) == 16, f"Expected 16 SegmentValue entries, got {len(values)}"
        for sv in values:
            assert isinstance(sv, SegmentValue)
            assert sv.verdict in ("Excellent", "Good", "Moderate", "Low", "N/A")

        # Surface sector should be N/A
        surface_vals = [v for v in values if v.verdict == "N/A"]
        assert len(surface_vals) >= 1, "At least 1 surface sector should have N/A verdict"

        # Long-haul segments should have high value
        # DOH-NRT is ~5,000+ miles, should be Excellent or Good
        doh_nrt = [v for v in values if v.route == "DOH-NRT"]
        assert len(doh_nrt) == 1
        assert doh_nrt[0].verdict in ("Excellent", "Good"), (
            f"DOH-NRT should be Excellent or Good, got {doh_nrt[0].verdict}"
        )

    def test_booking_returns_script(self, v3_itinerary):
        """BookingGenerator.generate returns a complete BookingScript."""
        itin = _build_itinerary(v3_itinerary)
        gen = BookingGenerator()
        script = gen.generate(itin)

        assert isinstance(script, BookingScript)
        # Opening should mention oneworld Explorer
        assert "oneworld Explorer" in script.opening
        # Should have 16 segment scripts
        assert len(script.segments) == 16
        # Closing should mention checklist items
        assert "CHECKLIST" in script.closing.upper()
        # GDS commands should be non-empty
        assert len(script.gds_commands) > 0
        # Should have ARNK for the surface sector
        assert "ARNK" in script.gds_commands

    def test_full_pipeline_no_exceptions(self, v3_itinerary):
        """Running all pipeline stages sequentially completes without error."""
        itin = _build_itinerary(v3_itinerary)

        # Stage 1: validate
        validator = Validator()
        report = validator.validate(itin)
        assert report.passed is True

        # Stage 2: cost
        estimator = CostEstimator()
        cost = estimator.estimate_total(itin)
        assert cost.total_per_person_usd > 0

        # Stage 3: NTP
        calc = NTPCalculator()
        ntp_list = calc.calculate(itin)
        assert len(ntp_list) == len(itin.segments)

        # Stage 4: value
        analyzer = SegmentValueAnalyzer()
        values = analyzer.analyze(itin)
        assert len(values) == len(itin.segments)

        # Stage 5: booking
        gen = BookingGenerator()
        script = gen.generate(itin)
        assert len(script.segments) == len(itin.segments)


# ---------------------------------------------------------------------------
# TestV3RuleDetails — Detailed rule-by-rule verification
# ---------------------------------------------------------------------------


class TestV3RuleDetails:
    """Detailed checks for each rule against the V3 fixture."""

    @pytest.fixture(autouse=True)
    def _setup(self, v3_itinerary):
        """Build itinerary, context, and validation report once per test."""
        self.itin = _build_itinerary(v3_itinerary)
        self.ctx = build_context(self.itin)
        self.validator = Validator()
        self.report = self.validator.validate(self.itin)
        self.results_by_id = {}
        for r in self.report.results:
            self.results_by_id.setdefault(r.rule_id, []).append(r)

    def _get_results(self, rule_id: str) -> list[RuleResult]:
        """Get results for a specific rule_id."""
        results = self.results_by_id.get(rule_id, [])
        assert results, f"No results found for rule_id={rule_id}"
        return results

    def test_segment_count_passes(self):
        """segment_count: 16 segments passes (max is 16)."""
        results = self._get_results("segment_count")
        assert all(r.passed for r in results), (
            f"segment_count should pass: {[r.message for r in results if not r.passed]}"
        )
        # Check message references 16
        assert any("16" in r.message for r in results)

    def test_per_continent_limit_passes(self):
        """per_continent_limit: all continents within their limits."""
        results = self._get_results("per_continent_limit")
        for r in results:
            assert r.passed, f"per_continent_limit failed: {r.message}"

    def test_direction_of_travel_eastbound(self):
        """direction_of_travel: eastbound passes."""
        results = self._get_results("direction_of_travel")
        assert all(r.passed for r in results), (
            f"direction_of_travel should pass: {[r.message for r in results if not r.passed]}"
        )
        # Verify eastbound is mentioned
        assert any("eastbound" in r.message.lower() for r in results), (
            f"Expected 'eastbound' in direction message: {[r.message for r in results]}"
        )

    def test_ocean_crossings_both_present(self):
        """ocean_crossings: both Pacific (NAN->SFO) and Atlantic (MEX->MAD) present."""
        results = self._get_results("ocean_crossings")
        # Should have 2 results (one for Pacific, one for Atlantic)
        assert len(results) == 2, f"Expected 2 ocean crossing results, got {len(results)}"
        assert all(r.passed for r in results), (
            f"ocean_crossings should all pass: {[r.message for r in results if not r.passed]}"
        )
        messages = " ".join(r.message for r in results)
        assert "Pacific" in messages, f"Expected 'Pacific' in messages: {messages}"
        assert "Atlantic" in messages, f"Expected 'Atlantic' in messages: {messages}"

    def test_minimum_stopovers_passes(self):
        """minimum_stopovers: V3 has well over 2 stopovers."""
        results = self._get_results("minimum_stopovers")
        assert all(r.passed for r in results)

    def test_origin_continent_stopovers_warning(self):
        """origin_continent_stopovers: WARNING expected for MAD stopover in EU_ME."""
        results = self._get_results("origin_continent_stopovers")
        # V3 has 3 stopovers in EU_ME: AMM, DOH, MAD (CAI is origin, MAD is stopover)
        # This should trigger a WARNING (not a VIOLATION)
        warnings = [r for r in results if not r.passed and r.severity == Severity.WARNING]
        assert len(warnings) >= 1, (
            f"Expected at least 1 WARNING for origin_continent_stopovers, "
            f"got: {[(r.passed, r.severity, r.message) for r in results]}"
        )
        # Must NOT be a VIOLATION
        violations = [r for r in results if not r.passed and r.severity == Severity.VIOLATION]
        assert len(violations) == 0, (
            f"origin_continent_stopovers should not VIOLATE, got: {[r.message for r in violations]}"
        )

    def test_same_city_resolution_detected(self):
        """same_city_resolution: NRT/HND and TSA/TPE detected as same-city."""
        results = self._get_results("same_city_resolution")
        messages = " ".join(r.message for r in results)
        # NRT/HND pair
        assert "NRT" in messages and "HND" in messages, (
            f"Expected NRT/HND same-city pair in messages: {messages}"
        )
        # TSA/TPE pair
        assert "TSA" in messages and "TPE" in messages, (
            f"Expected TSA/TPE same-city pair in messages: {messages}"
        )
        # All should pass (same-city is INFO, not a failure)
        assert all(r.passed for r in results)

    def test_hemisphere_revisit_passes(self):
        """hemisphere_revisit: no backtracking detected."""
        results = self._get_results("hemisphere_revisit")
        assert all(r.passed for r in results), (
            f"hemisphere_revisit should pass: {[r.message for r in results if not r.passed]}"
        )

    def test_eligible_carriers_passes(self):
        """eligible_carriers: all carriers (RJ, QR, JL, CX, FJ, AA, IB) are oneworld."""
        results = self._get_results("eligible_carriers")
        assert all(r.passed for r in results), (
            f"eligible_carriers should pass: {[r.message for r in results if not r.passed]}"
        )

    def test_qr_not_first_passes(self):
        """qr_not_first: first carrier is RJ (not QR)."""
        results = self._get_results("qr_not_first")
        assert all(r.passed for r in results), (
            f"qr_not_first should pass: {[r.message for r in results if not r.passed]}"
        )
        # Should mention RJ
        assert any("RJ" in r.message for r in results)

    def test_return_to_origin_passes(self):
        """return_to_origin: MAD->CAI returns to origin CAI."""
        results = self._get_results("return_to_origin")
        assert all(r.passed for r in results), (
            f"return_to_origin should pass: {[r.message for r in results if not r.passed]}"
        )

    def test_continent_count_matches_done4(self):
        """continent_count: 4 continents matches DONE4."""
        results = self._get_results("continent_count")
        assert all(r.passed for r in results), (
            f"continent_count should pass: {[r.message for r in results if not r.passed]}"
        )
        # Message should mention 4 continents
        assert any("4" in r.message for r in results)

    def test_ticket_validity_passes(self):
        """ticket_validity: trip duration is within 10-365 days."""
        results = self._get_results("ticket_validity")
        assert all(r.passed for r in results), (
            f"ticket_validity should pass: {[r.message for r in results if not r.passed]}"
        )

    def test_hawaii_alaska_passes(self):
        """hawaii_alaska: V3 doesn't visit Hawaii or Alaska."""
        results = self._get_results("hawaii_alaska")
        assert all(r.passed for r in results)

    def test_transcontinental_us_passes(self):
        """transcontinental_us: SFO->JFK is 1 transcontinental (limit 1)."""
        results = self._get_results("transcontinental_us")
        assert all(r.passed for r in results)

    def test_no_violations_only_warnings(self):
        """Overall: 0 violations, at least 1 warning."""
        assert self.report.violation_count == 0
        assert self.report.warning_count >= 1
        # All warnings should be WARNING severity
        for w in self.report.warnings:
            assert w.severity == Severity.WARNING

    def test_every_registered_rule_produces_results(self):
        """Every registered rule should produce at least one result."""
        result_rule_ids = {r.rule_id for r in self.report.results}
        registered_rule_ids = {r().rule_id for r in get_registered_rules()}
        missing = registered_rule_ids - result_rule_ids
        assert not missing, f"Rules produced no results: {missing}"


# ---------------------------------------------------------------------------
# TestV3Geography — Geography-specific checks
# ---------------------------------------------------------------------------


class TestV3Geography:
    """Geography-specific verification for the V3 fixture."""

    @pytest.fixture(autouse=True)
    def _setup(self, v3_itinerary):
        self.itin = _build_itinerary(v3_itinerary)
        self.ctx = build_context(self.itin)

    def test_continent_assignments_all_16(self):
        """Every segment has a continent assignment (none are None)."""
        assert len(self.ctx.segment_continents) == 16
        for i, cont in enumerate(self.ctx.segment_continents):
            assert cont is not None, (
                f"Segment {i} ({self.itin.segments[i].from_airport}->"
                f"{self.itin.segments[i].to_airport}) has no continent"
            )

    def test_eu_me_segments(self):
        """EU_ME segments: CAI->AMM, AMM->DOH, MEX->MAD, MAD->CAI."""
        eu_me_indices = [
            i for i, c in enumerate(self.ctx.segment_continents) if c == Continent.EU_ME
        ]
        # Segments 0 (CAI->AMM), 1 (AMM->DOH), 14 (MEX->MAD), 15 (MAD->CAI)
        assert len(eu_me_indices) == 4, (
            f"Expected 4 EU_ME segments, got {len(eu_me_indices)}: "
            f"{[(i, self.itin.segments[i].from_airport, self.itin.segments[i].to_airport) for i in eu_me_indices]}"
        )

    def test_asia_segments(self):
        """Asia segments: DOH->NRT, HND->TSA, TPE->HKG, HKG->SIN."""
        asia_indices = [i for i, c in enumerate(self.ctx.segment_continents) if c == Continent.ASIA]
        assert len(asia_indices) == 4, (
            f"Expected 4 Asia segments, got {len(asia_indices)}: "
            f"{[(i, self.itin.segments[i].from_airport, self.itin.segments[i].to_airport) for i in asia_indices]}"
        )

    def test_swp_segments(self):
        """SWP segments: SIN->NAN, NAN->FUN, FUN->NAN."""
        swp_indices = [i for i, c in enumerate(self.ctx.segment_continents) if c == Continent.SWP]
        # Segments 6 (SIN->NAN), 7 (NAN->FUN), 8 (FUN->NAN) = 3
        assert 3 <= len(swp_indices) <= 4, (
            f"Expected 3-4 SWP segments, got {len(swp_indices)}: "
            f"{[(i, self.itin.segments[i].from_airport, self.itin.segments[i].to_airport) for i in swp_indices]}"
        )

    def test_n_america_segments(self):
        """N_America segments: NAN->SFO, SFO->JFK, JFK->MCO, MCO->MIA, MIA->MEX."""
        na_indices = [
            i for i, c in enumerate(self.ctx.segment_continents) if c == Continent.N_AMERICA
        ]
        # Segments 9 (NAN->SFO), 10 (SFO->JFK), 11 (JFK->MCO surface),
        # 12 (MCO->MIA), 13 (MIA->MEX) = 4-5 depending on surface counting
        assert 4 <= len(na_indices) <= 6, (
            f"Expected 4-6 N_America segments, got {len(na_indices)}: "
            f"{[(i, self.itin.segments[i].from_airport, self.itin.segments[i].to_airport) for i in na_indices]}"
        )

    def test_tc_sequence_eastbound(self):
        """TC sequence follows eastbound: TC2 -> TC3 -> TC1 -> TC2."""
        tc_seq = self.ctx.tc_sequence
        assert len(tc_seq) >= 4, f"Expected >= 4 TC transitions, got {len(tc_seq)}: {tc_seq}"
        # First should be TC2 (origin continent EU_ME)
        assert tc_seq[0] == TariffConference.TC2, f"First TC should be TC2, got {tc_seq[0]}"
        # Should include TC3 (Asia/SWP)
        assert TariffConference.TC3 in tc_seq, "TC3 should be in TC sequence"
        # Should include TC1 (N_America)
        assert TariffConference.TC1 in tc_seq, "TC1 should be in TC sequence"
        # Last should be TC2 (return to EU_ME)
        assert tc_seq[-1] == TariffConference.TC2, f"Last TC should be TC2, got {tc_seq[-1]}"

    def test_same_city_pairs_count(self):
        """Exactly 2 same-city pairs: NRT/HND (Tokyo) and TSA/TPE (Taipei)."""
        assert len(self.ctx.same_city_pairs) == 2, (
            f"Expected 2 same-city pairs, got {len(self.ctx.same_city_pairs)}"
        )

    def test_same_city_nrt_hnd(self):
        """NRT->HND is a same-city pair (Tokyo)."""
        # Segment 2: DOH->NRT, Segment 3: HND->TSA
        # Same-city pair at (2, 3)
        pair_segments = self.ctx.same_city_pairs
        airports = [
            (self.itin.segments[a].to_airport, self.itin.segments[b].from_airport)
            for a, b in pair_segments
        ]
        assert ("NRT", "HND") in airports, f"Expected NRT/HND in same-city pairs, got: {airports}"

    def test_same_city_tsa_tpe(self):
        """TSA->TPE is a same-city pair (Taipei)."""
        pair_segments = self.ctx.same_city_pairs
        airports = [
            (self.itin.segments[a].to_airport, self.itin.segments[b].from_airport)
            for a, b in pair_segments
        ]
        assert ("TSA", "TPE") in airports, f"Expected TSA/TPE in same-city pairs, got: {airports}"

    def test_same_city_not_surface_sectors(self):
        """Same-city transitions are NOT counted as surface sectors."""
        # Segments 3 (HND->TSA) and 4 (TPE->HKG) should not be surface
        seg_3 = self.itin.segments[3]
        seg_4 = self.itin.segments[4]
        assert not seg_3.is_surface, f"HND->TSA should not be surface, got type={seg_3.type}"
        assert not seg_4.is_surface, f"TPE->HKG should not be surface, got type={seg_4.type}"

    def test_origin_continent_is_eu_me(self):
        """Origin (CAI) is in EU_ME."""
        assert self.ctx.origin_continent == Continent.EU_ME
        assert self.ctx.origin_tc == TariffConference.TC2

    def test_continents_visited_count(self):
        """Visits exactly 4 continents."""
        assert len(self.ctx.continents_visited) == 4
        visited_set = set(self.ctx.continents_visited)
        expected = {Continent.EU_ME, Continent.ASIA, Continent.SWP, Continent.N_AMERICA}
        assert visited_set == expected, f"Expected {expected}, got {visited_set}"

    def test_pacific_crossing_segment(self):
        """NAN->SFO is the Pacific crossing (TC3->TC1)."""
        seg = self.itin.segments[9]  # NAN->SFO
        assert seg.from_airport == "NAN"
        assert seg.to_airport == "SFO"
        from_cont = get_continent("NAN")
        to_cont = get_continent("SFO")
        assert CONTINENT_TO_TC[from_cont] == TariffConference.TC3
        assert CONTINENT_TO_TC[to_cont] == TariffConference.TC1

    def test_atlantic_crossing_segment(self):
        """MEX->MAD is the Atlantic crossing (TC1->TC2)."""
        seg = self.itin.segments[14]  # MEX->MAD
        assert seg.from_airport == "MEX"
        assert seg.to_airport == "MAD"
        from_cont = get_continent("MEX")
        to_cont = get_continent("MAD")
        assert CONTINENT_TO_TC[from_cont] == TariffConference.TC1
        assert CONTINENT_TO_TC[to_cont] == TariffConference.TC2

    def test_stopovers_per_continent(self):
        """Verify stopovers per continent match expectations."""
        spc = self.ctx.stopovers_per_continent
        # EU_ME stopovers: AMM (#0), DOH (#1), MAD (#14) = 3
        assert spc.get(Continent.EU_ME, 0) >= 3, (
            f"Expected >= 3 EU_ME stopovers, got {spc.get(Continent.EU_ME, 0)}"
        )
        # Asia stopovers: NRT (#2), TSA (#3), HKG (#4) = 3
        assert spc.get(Continent.ASIA, 0) >= 2
        # SWP stopovers: NAN (#6), FUN (#7) = 2
        assert spc.get(Continent.SWP, 0) >= 1
        # N_America stopovers: SFO (#10), JFK (#10 area), MEX (#13) = 2-3
        assert spc.get(Continent.N_AMERICA, 0) >= 2


# ---------------------------------------------------------------------------
# TestCleanItinerary — Variant with no warnings
# ---------------------------------------------------------------------------


class TestCleanItinerary:
    """Test a simpler itinerary that passes ALL rules with 0 warnings."""

    def test_clean_itinerary_zero_violations(self):
        """Clean itinerary passes with 0 violations."""
        itin = _make_clean_itinerary()
        validator = Validator()
        report = validator.validate(itin)

        assert report.passed is True, "Expected PASS, got violations: " + "; ".join(
            f"[{v.rule_id}] {v.message}" for v in report.violations
        )
        assert report.violation_count == 0

    def test_clean_itinerary_zero_warnings(self):
        """Clean itinerary has 0 warnings (origin continent stopovers <= 2)."""
        itin = _make_clean_itinerary()
        validator = Validator()
        report = validator.validate(itin)

        if report.warning_count > 0:
            warning_details = "; ".join(f"[{w.rule_id}] {w.message}" for w in report.warnings)
            pytest.fail(f"Expected 0 warnings but got {report.warning_count}: {warning_details}")

    def test_clean_itinerary_visits_4_continents(self):
        """Clean itinerary visits EU_ME, Asia, SWP, N_America."""
        itin = _make_clean_itinerary()
        ctx = build_context(itin)
        assert len(ctx.continents_visited) == 4
        visited_set = set(ctx.continents_visited)
        expected = {Continent.EU_ME, Continent.ASIA, Continent.SWP, Continent.N_AMERICA}
        assert visited_set == expected

    def test_clean_itinerary_origin_stopovers_at_most_2(self):
        """Clean itinerary has <= 2 stopovers in origin continent."""
        itin = _make_clean_itinerary()
        ctx = build_context(itin)
        origin_stopovers = ctx.stopovers_per_continent.get(ctx.origin_continent, 0)
        assert origin_stopovers <= 2, (
            f"Expected <= 2 origin continent stopovers, got {origin_stopovers}"
        )

    def test_clean_itinerary_full_pipeline(self):
        """Full pipeline succeeds on the clean itinerary."""
        itin = _make_clean_itinerary()

        validator = Validator()
        report = validator.validate(itin)
        assert report.passed is True

        estimator = CostEstimator()
        cost = estimator.estimate_total(itin)
        assert cost.total_per_person_usd > 0

        calc = NTPCalculator()
        ntp_list = calc.calculate(itin)
        assert len(ntp_list) == len(itin.segments)

        analyzer = SegmentValueAnalyzer()
        values = analyzer.analyze(itin)
        assert len(values) == len(itin.segments)

        gen = BookingGenerator()
        script = gen.generate(itin)
        assert len(script.segments) == len(itin.segments)


# ---------------------------------------------------------------------------
# TestNoMileageCap — Verify 34,000nm cap NOT enforced
# ---------------------------------------------------------------------------


class TestNoMileageCap:
    """Verify that there is NO 34,000nm distance cap rule."""

    def test_no_distance_cap_rule_id(self):
        """No registered rule has 'distance_cap' or 'mileage_cap' as rule_id."""
        _ = Validator()  # Trigger rule registration
        all_ids = {r().rule_id for r in get_registered_rules()}
        assert "distance_cap" not in all_ids, "distance_cap rule should not exist"
        assert "mileage_cap" not in all_ids, "mileage_cap rule should not exist"

    def test_no_distance_related_violations(self, v3_itinerary):
        """V3 produces no results mentioning 34,000nm or mileage cap."""
        itin = _build_itinerary(v3_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        for r in report.results:
            assert "34,000" not in r.message, f"Rule {r.rule_id} mentions 34,000nm cap"
            assert "34000" not in r.message, f"Rule {r.rule_id} mentions 34000nm cap"
            assert "mileage cap" not in r.message.lower(), f"Rule {r.rule_id} mentions mileage cap"

    def test_no_distance_rule_keyword_in_rule_names(self):
        """No rule name or ID references distance limits."""
        _ = Validator()
        for rule_cls in get_registered_rules():
            rule = rule_cls()
            rule_id_lower = rule.rule_id.lower()
            rule_name_lower = rule.rule_name.lower()
            assert "distance_cap" not in rule_id_lower
            assert "mileage_cap" not in rule_id_lower
            assert "distance cap" not in rule_name_lower
            assert "mileage cap" not in rule_name_lower

    def test_long_itinerary_no_distance_violation(self):
        """Even an itinerary covering huge distances produces no distance violation."""
        # LHR -> SYD -> LAX -> LHR would be 20,000+ miles
        itin = Itinerary(
            ticket=Ticket(type="DONE4", cabin="business", origin="LHR"),
            segments=[
                Segment(
                    **{
                        "from": "LHR",
                        "to": "NRT",
                        "carrier": "BA",
                        "date": "2026-04-01",
                        "type": "stopover",
                    }
                ),
                Segment(
                    **{
                        "from": "NRT",
                        "to": "SYD",
                        "carrier": "QF",
                        "date": "2026-04-05",
                        "type": "stopover",
                    }
                ),
                Segment(
                    **{
                        "from": "SYD",
                        "to": "LAX",
                        "carrier": "QF",
                        "date": "2026-04-10",
                        "type": "stopover",
                    }
                ),
                Segment(
                    **{
                        "from": "LAX",
                        "to": "JFK",
                        "carrier": "AA",
                        "date": "2026-04-14",
                        "type": "stopover",
                    }
                ),
                Segment(
                    **{
                        "from": "JFK",
                        "to": "LHR",
                        "carrier": "BA",
                        "date": "2026-04-18",
                        "type": "final",
                    }
                ),
            ],
        )
        validator = Validator()
        report = validator.validate(itin)

        # Check no distance-related violations
        for r in report.results:
            if not r.passed and r.severity == Severity.VIOLATION:
                assert "distance" not in r.message.lower(), (
                    f"Unexpected distance violation: {r.message}"
                )
                assert "mileage" not in r.message.lower(), (
                    f"Unexpected mileage violation: {r.message}"
                )


# ---------------------------------------------------------------------------
# TestInvalidFixtures — Fixture-based invalid itinerary tests (T047)
# ---------------------------------------------------------------------------


class TestInvalidFixtures:
    """Test that invalid YAML fixtures produce the expected violations."""

    def test_qr_first_fails(self, qr_first_itinerary):
        """QR as first carrier triggers qr_not_first violation."""
        itin = _build_itinerary(qr_first_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        assert report.passed is False, "Expected validation to FAIL for QR-first itinerary"

        qr_violations = [v for v in report.violations if v.rule_id == "qr_not_first"]
        assert len(qr_violations) >= 1, (
            "Expected qr_not_first violation, got violations: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in report.violations)
        )
        assert "QR" in qr_violations[0].message or "Qatar" in qr_violations[0].message

    def test_hawaii_backtrack_fails(self, hawaii_backtrack_itinerary):
        """Hawaii backtracking triggers hawaii_alaska violation."""
        itin = _build_itinerary(hawaii_backtrack_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        assert report.passed is False, "Expected validation to FAIL for Hawaii backtrack itinerary"

        hawaii_violations = [v for v in report.violations if v.rule_id == "hawaii_alaska"]
        assert len(hawaii_violations) >= 1, (
            "Expected hawaii_alaska violation, got violations: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in report.violations)
        )
        assert (
            "Hawaii" in hawaii_violations[0].message
            or "backtrack" in hawaii_violations[0].message.lower()
        )

    def test_too_many_segments_fails(self, too_many_segments_itinerary):
        """17 segments triggers segment_count violation."""
        itin = _build_itinerary(too_many_segments_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        assert report.passed is False, "Expected validation to FAIL for 17-segment itinerary"

        seg_violations = [v for v in report.violations if v.rule_id == "segment_count"]
        assert len(seg_violations) >= 1, (
            "Expected segment_count violation, got violations: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in report.violations)
        )
        assert "17" in seg_violations[0].message
        assert "16" in seg_violations[0].message

    def test_minimal_valid_passes(self, minimal_valid_itinerary):
        """Minimal valid itinerary passes with 0 violations and 0 warnings."""
        itin = _build_itinerary(minimal_valid_itinerary)
        validator = Validator()
        report = validator.validate(itin)

        assert report.passed is True, (
            f"Expected PASS, got {report.violation_count} violations: "
            + "; ".join(f"[{v.rule_id}] {v.message}" for v in report.violations)
        )
        assert report.violation_count == 0

        if report.warning_count > 0:
            warning_details = "; ".join(f"[{w.rule_id}] {w.message}" for w in report.warnings)
            pytest.fail(f"Expected 0 warnings but got {report.warning_count}: {warning_details}")
