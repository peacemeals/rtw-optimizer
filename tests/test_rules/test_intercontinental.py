"""Tests for intercontinental classification and IntercontinentalLimitRule."""

import yaml
from pathlib import Path

from rtw.models import Continent, Itinerary, Ticket, Segment, Severity
from rtw.rules.intercontinental import IntercontinentalLimitRule
from rtw.rules.segments import PerContinentLimitRule
from rtw.validator import Validator, build_context

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make_itinerary(segments_data: list[dict], origin="CAI", ticket_type="DONE4") -> Itinerary:
    """Helper to build itinerary from segment dicts."""
    ticket = Ticket(type=ticket_type, cabin="business", origin=origin)
    segments = [Segment(**s) for s in segments_data]
    return Itinerary(ticket=ticket, segments=segments)


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return yaml.safe_load(f)


# ===== Group 1: Intercontinental Classification in build_context =====


class TestIntercontinentalClassification:
    def test_same_continent_not_intercontinental(self):
        """HKG->DEL (Asia->Asia) is NOT intercontinental."""
        itin = _make_itinerary([{"from": "HKG", "to": "DEL", "carrier": "CX"}])
        ctx = build_context(itin)
        assert ctx.is_intercontinental[0] is False

    def test_cross_continent_same_tc_is_intercontinental(self):
        """LHR->JNB (EU_ME->Africa, both TC2) IS intercontinental."""
        itin = _make_itinerary([{"from": "LHR", "to": "JNB", "carrier": "BA"}])
        ctx = build_context(itin)
        assert ctx.is_intercontinental[0] is True

    def test_cross_continent_diff_tc_is_intercontinental(self):
        """JFK->LHR (N_America->EU_ME, TC1->TC2) IS intercontinental."""
        itin = _make_itinerary([{"from": "JFK", "to": "LHR", "carrier": "BA"}])
        ctx = build_context(itin)
        assert ctx.is_intercontinental[0] is True

    def test_cross_tc3_continents_is_intercontinental(self):
        """SYD->HKG (SWP->Asia, both TC3) IS intercontinental."""
        itin = _make_itinerary([{"from": "SYD", "to": "HKG", "carrier": "CX"}])
        ctx = build_context(itin)
        assert ctx.is_intercontinental[0] is True

    def test_cross_tc1_continents_is_intercontinental(self):
        """MIA->GRU (N_America->S_America, both TC1) IS intercontinental."""
        itin = _make_itinerary([{"from": "MIA", "to": "GRU", "carrier": "AA"}])
        ctx = build_context(itin)
        assert ctx.is_intercontinental[0] is True

    def test_intercontinental_excluded_from_per_continent(self):
        """JNB->HKG (intercontinental) + HKG->DEL (intra) => Asia segments = 1."""
        itin = _make_itinerary([
            {"from": "JNB", "to": "HKG", "carrier": "CX"},
            {"from": "HKG", "to": "DEL", "carrier": "CX"},
        ], origin="JNB")
        ctx = build_context(itin)
        assert ctx.segments_per_continent.get(Continent.ASIA, 0) == 1

    def test_intra_continental_counted_in_per_continent(self):
        """HKG->DEL + DEL->KUL (both intra-Asia) => Asia segments = 2."""
        itin = _make_itinerary([
            {"from": "HKG", "to": "DEL", "carrier": "CX"},
            {"from": "DEL", "to": "KUL", "carrier": "MH"},
        ])
        ctx = build_context(itin)
        assert ctx.segments_per_continent[Continent.ASIA] == 2

    def test_intercontinental_arrivals_counted(self):
        """JNB->HKG counts as 1 arrival in Asia, 1 departure from Africa."""
        itin = _make_itinerary([
            {"from": "JNB", "to": "HKG", "carrier": "CX"},
        ], origin="JNB")
        ctx = build_context(itin)
        assert ctx.intercontinental_arrivals.get(Continent.ASIA, 0) == 1
        assert ctx.intercontinental_departures.get(Continent.AFRICA, 0) == 1

    def test_stopovers_still_counted_for_intercontinental(self):
        """JNB->HKG (stopover, intercontinental) still counts as Asia stopover."""
        itin = _make_itinerary([
            {"from": "JNB", "to": "HKG", "carrier": "CX", "type": "stopover"},
        ], origin="JNB")
        ctx = build_context(itin)
        assert ctx.stopovers_per_continent.get(Continent.ASIA, 0) == 1

    def test_surface_sector_intercontinental(self):
        """A surface segment crossing continents is still intercontinental."""
        itin = _make_itinerary([
            {"from": "JFK", "to": "LHR", "carrier": "BA", "type": "surface"},
        ])
        ctx = build_context(itin)
        assert ctx.is_intercontinental[0] is True


# ===== Group 2: JNB Fixture End-to-End =====


class TestJNBFixture:
    """Tests for the JNB business routing that was previously failing."""

    @staticmethod
    def _load_jnb():
        data = _load_fixture("flyertalk_jnb_business.yaml")
        return Itinerary(**data)

    def test_jnb_asia_intra_count_is_4(self):
        """4 intra-Asia segments: HKG->DEL, DEL->KUL, KUL->SIN, SIN->NRT."""
        itin = self._load_jnb()
        ctx = build_context(itin)
        assert ctx.segments_per_continent.get(Continent.ASIA, 0) == 4

    def test_jnb_na_intra_count_is_3(self):
        """3 intra-NA segments: HNL->LAX, LAX->SFO, SFO->JFK."""
        itin = self._load_jnb()
        ctx = build_context(itin)
        assert ctx.segments_per_continent.get(Continent.N_AMERICA, 0) == 3

    def test_jnb_africa_intra_count_is_0(self):
        """No intra-Africa segments (JNB->HKG and LHR->JNB are intercontinental)."""
        itin = self._load_jnb()
        ctx = build_context(itin)
        assert ctx.segments_per_continent.get(Continent.AFRICA, 0) == 0

    def test_jnb_eu_me_intra_count_is_0(self):
        """No intra-EU/ME segments (JFK->LHR and LHR->JNB are intercontinental)."""
        itin = self._load_jnb()
        ctx = build_context(itin)
        assert ctx.segments_per_continent.get(Continent.EU_ME, 0) == 0

    def test_jnb_intercontinental_arrivals(self):
        """JNB routing has 4 intercontinental arrivals in 4 different continents."""
        itin = self._load_jnb()
        ctx = build_context(itin)
        assert ctx.intercontinental_arrivals.get(Continent.ASIA, 0) == 1
        assert ctx.intercontinental_arrivals.get(Continent.N_AMERICA, 0) == 1
        assert ctx.intercontinental_arrivals.get(Continent.EU_ME, 0) == 1
        assert ctx.intercontinental_arrivals.get(Continent.AFRICA, 0) == 1

    def test_jnb_intercontinental_departures(self):
        """JNB routing has 4 intercontinental departures from 4 continents."""
        itin = self._load_jnb()
        ctx = build_context(itin)
        assert ctx.intercontinental_departures.get(Continent.AFRICA, 0) == 1
        assert ctx.intercontinental_departures.get(Continent.ASIA, 0) == 1
        assert ctx.intercontinental_departures.get(Continent.N_AMERICA, 0) == 1
        assert ctx.intercontinental_departures.get(Continent.EU_ME, 0) == 1

    def test_jnb_passes_per_continent_limit(self):
        """JNB routing passes per-continent limit (Asia=4/4, NA=3/6)."""
        itin = self._load_jnb()
        ctx = build_context(itin)
        results = PerContinentLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed and r.severity == Severity.VIOLATION]
        assert len(violations) == 0

    def test_jnb_passes_intercontinental_limit(self):
        """JNB routing passes intercontinental limit (1/1 each, except NA 1/2)."""
        itin = self._load_jnb()
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        assert len(violations) == 0

    def test_jnb_full_validation_passes(self):
        """JNB routing passes full validation."""
        itin = self._load_jnb()
        report = Validator().validate(itin)
        assert report.passed, (
            f"JNB routing should pass but got violations: "
            f"{[v.message for v in report.violations]}"
        )


# ===== Group 3: IntercontinentalLimitRule Violations =====


class TestIntercontinentalLimitViolations:
    def test_two_arrivals_in_asia_default_fails(self):
        """2 IC arrivals in Asia without SWP/EU_ME bridge => violation."""
        # Route: JNB->HKG, HKG->DEL, DEL->KUL, SIN->NRT (all Asia),
        # then NRT->SFO (depart Asia), SFO->NRT (arrive Asia again)
        # But without SWP and EU_ME visited, Asia limit is 1
        itin = _make_itinerary([
            {"from": "JNB", "to": "HKG", "carrier": "CX"},  # IC arrival Asia #1
            {"from": "HKG", "to": "NRT", "carrier": "CX"},  # intra-Asia
            {"from": "NRT", "to": "SFO", "carrier": "JL"},  # IC depart Asia
            {"from": "SFO", "to": "NRT", "carrier": "JL"},  # IC arrival Asia #2
            {"from": "NRT", "to": "JNB", "carrier": "CX"},  # IC depart Asia
        ], origin="JNB", ticket_type="DONE3")
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        # Asia should have violations (2 arrivals, 2 departures, limit 1)
        assert len(violations) > 0
        asia_violations = [r for r in violations if "Asia" in r.message]
        assert len(asia_violations) > 0

    def test_two_arrivals_in_asia_bridge_passes(self):
        """2 IC arrivals in Asia WITH SWP+EU_ME => passes (bridge exception)."""
        itin = _make_itinerary([
            {"from": "SYD", "to": "HKG", "carrier": "CX"},  # IC arr Asia #1 (from SWP)
            {"from": "HKG", "to": "LHR", "carrier": "CX"},  # IC dep Asia (to EU_ME)
            {"from": "LHR", "to": "JFK", "carrier": "BA"},  # IC dep EU_ME
            {"from": "JFK", "to": "NRT", "carrier": "JL"},  # IC arr Asia #2 (from NA)
            {"from": "NRT", "to": "SYD", "carrier": "QF"},  # IC dep Asia (to SWP)
        ], origin="SYD", ticket_type="DONE4")
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        asia_violations = [r for r in violations if "Asia" in r.message]
        assert len(asia_violations) == 0

    def test_two_arrivals_in_na_passes(self):
        """2 IC arrivals in N_America => passes (NA always allows 2)."""
        itin = _make_itinerary([
            {"from": "LHR", "to": "JFK", "carrier": "BA"},  # IC arr NA #1
            {"from": "JFK", "to": "NRT", "carrier": "JL"},  # IC dep NA
            {"from": "NRT", "to": "SFO", "carrier": "JL"},  # IC arr NA #2
            {"from": "SFO", "to": "LHR", "carrier": "BA"},  # IC dep NA
        ], origin="LHR", ticket_type="DONE3")
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        na_violations = [r for r in violations if "N_America" in r.message]
        assert len(na_violations) == 0

    def test_three_arrivals_in_na_fails(self):
        """3 IC arrivals in N_America => violation (NA limit is 2)."""
        itin = _make_itinerary([
            {"from": "LHR", "to": "JFK", "carrier": "BA"},  # IC arr NA #1
            {"from": "JFK", "to": "NRT", "carrier": "JL"},  # IC dep NA
            {"from": "NRT", "to": "SFO", "carrier": "JL"},  # IC arr NA #2
            {"from": "SFO", "to": "LHR", "carrier": "BA"},  # IC dep NA
            {"from": "LHR", "to": "LAX", "carrier": "BA"},  # IC arr NA #3
        ], origin="LHR", ticket_type="DONE3")
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        na_violations = [r for r in violations if "N_America" in r.message]
        assert len(na_violations) > 0

    def test_two_departures_in_eu_me_with_africa_passes(self):
        """2 IC departures from EU/ME with Africa visited => passes."""
        itin = _make_itinerary([
            {"from": "JNB", "to": "LHR", "carrier": "BA"},  # IC arr EU_ME (from Africa)
            {"from": "LHR", "to": "JFK", "carrier": "BA"},  # IC dep EU_ME #1
            {"from": "JFK", "to": "MAD", "carrier": "IB"},  # IC arr EU_ME
            {"from": "MAD", "to": "JNB", "carrier": "BA"},  # IC dep EU_ME #2 (to Africa)
        ], origin="JNB", ticket_type="DONE3")
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        eu_violations = [r for r in violations if "EU_ME" in r.message]
        assert len(eu_violations) == 0

    def test_two_departures_in_eu_me_without_africa_fails(self):
        """2 IC departures from EU/ME without Africa => violation."""
        itin = _make_itinerary([
            {"from": "NRT", "to": "LHR", "carrier": "BA"},  # IC arr EU_ME
            {"from": "LHR", "to": "JFK", "carrier": "BA"},  # IC dep EU_ME #1
            {"from": "JFK", "to": "MAD", "carrier": "IB"},  # IC arr EU_ME
            {"from": "MAD", "to": "NRT", "carrier": "JL"},  # IC dep EU_ME #2
        ], origin="NRT", ticket_type="DONE3")
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        eu_violations = [r for r in violations if "EU_ME" in r.message]
        assert len(eu_violations) > 0

    def test_no_intercontinental_segments_passes(self):
        """All intra-continental => passes with info message."""
        itin = _make_itinerary([
            {"from": "HKG", "to": "DEL", "carrier": "CX"},
            {"from": "DEL", "to": "KUL", "carrier": "MH"},
        ])
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        assert all(r.passed for r in results)
        assert "No intercontinental" in results[0].message


# ===== Group 4: V3 Fixture Regression =====


class TestV3Regression:
    """Ensure V3 fixture still passes after intercontinental changes."""

    @staticmethod
    def _load_v3():
        data = _load_fixture("valid_v3.yaml")
        return Itinerary(**data)

    def test_v3_per_continent_still_passes(self):
        itin = self._load_v3()
        ctx = build_context(itin)
        results = PerContinentLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed and r.severity == Severity.VIOLATION]
        assert len(violations) == 0

    def test_v3_intercontinental_limit_passes(self):
        itin = self._load_v3()
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        assert len(violations) == 0

    def test_v3_new_segments_per_continent_values(self):
        """After excluding intercontinental, V3 counts should be lower."""
        itin = self._load_v3()
        ctx = build_context(itin)
        # DOH->NRT (EU->Asia), SIN->NAN (Asia->SWP), NAN->SFO (SWP->NA),
        # MEX->MAD (NA->EU) are all intercontinental and excluded
        assert ctx.segments_per_continent.get(Continent.EU_ME, 0) == 3
        assert ctx.segments_per_continent.get(Continent.ASIA, 0) == 3
        assert ctx.segments_per_continent.get(Continent.SWP, 0) == 2
        assert ctx.segments_per_continent.get(Continent.N_AMERICA, 0) == 4


# ===== Group 5: MEL Westbound Fixture =====


class TestMELFixture:
    """Test the MEL westbound fixture which has multiple intercontinental crossings."""

    @staticmethod
    def _load_mel():
        data = _load_fixture("flyertalk_mel_westbound.yaml")
        return Itinerary(**data)

    def test_mel_passes_full_validation(self):
        itin = self._load_mel()
        report = Validator().validate(itin)
        assert report.passed, (
            f"MEL routing should pass but got violations: "
            f"{[v.message for v in report.violations]}"
        )

    def test_mel_passes_intercontinental_limit(self):
        itin = self._load_mel()
        ctx = build_context(itin)
        results = IntercontinentalLimitRule().check(itin, ctx)
        violations = [r for r in results if not r.passed]
        assert len(violations) == 0
