"""Validation tests for 5 real-world oneworld Explorer itineraries.

Sources:
- BUD: FlyerTalk oneworld Explorer First Timer (2022)
- SYD 6-continent: Karryon 7 Amazing Journeys
- HND First Class: FlyerTalk Oneworld Explorer User Guide
- LHR Eastbound: oneworld.com official sample
- OSL Eastbound: FlyerTalk ex-OSL DONE4 Help
"""

import yaml
from pathlib import Path

from rtw.models import Continent, Itinerary, Severity
from rtw.validator import Validator, build_context

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> Itinerary:
    with open(FIXTURES_DIR / name) as f:
        return Itinerary(**yaml.safe_load(f))


# ===== BUD DONE5 Westbound (16 segments, 5 continents incl. S.America) =====


class TestBUDWestbound:
    FIXTURE = "flyertalk_bud_westbound.yaml"

    def test_full_validation_passes(self):
        itin = _load(self.FIXTURE)
        report = Validator().validate(itin)
        assert report.passed, (
            f"BUD routing should pass but got violations: "
            f"{[v.message for v in report.violations]}"
        )

    def test_16_segments(self):
        itin = _load(self.FIXTURE)
        assert len(itin.segments) == 16

    def test_5_continents_visited(self):
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        visited = set(ctx.continents_visited)
        assert visited == {
            Continent.EU_ME,
            Continent.S_AMERICA,
            Continent.N_AMERICA,
            Continent.SWP,
            Continent.ASIA,
        }

    def test_intercontinental_counts(self):
        """5 IC crossings, each continent 1 arrival + 1 departure."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        # LHR(EU)->SCL(SA), SCL(SA)->MIA(NA), HNL(NA)->SYD(SWP),
        # AKL(SWP)->KUL(Asia), DEL(Asia)->DOH(EU)
        assert ctx.intercontinental_arrivals.get(Continent.S_AMERICA, 0) == 1
        assert ctx.intercontinental_arrivals.get(Continent.N_AMERICA, 0) == 1
        assert ctx.intercontinental_arrivals.get(Continent.SWP, 0) == 1
        assert ctx.intercontinental_arrivals.get(Continent.ASIA, 0) == 1
        assert ctx.intercontinental_arrivals.get(Continent.EU_ME, 0) == 1

    def test_per_continent_intra_segments(self):
        """Intra-continental counts after excluding intercontinental."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        # EU_ME: BUD->LHR, DOH->AMM, AMM->LHR, LHR->BUD = 4 (at the limit!)
        assert ctx.segments_per_continent.get(Continent.EU_ME, 0) == 4
        # N_America: MIA->ORD, ORD->ANC, ANC->HNL = 3
        assert ctx.segments_per_continent.get(Continent.N_AMERICA, 0) == 3
        # SWP: SYD->NAN, NAN->SYD, SYD->AKL = 3
        assert ctx.segments_per_continent.get(Continent.SWP, 0) == 3
        # Asia: KUL->DEL = 1
        assert ctx.segments_per_continent.get(Continent.ASIA, 0) == 1
        # S_America: 0 (SCL only via IC flights)
        assert ctx.segments_per_continent.get(Continent.S_AMERICA, 0) == 0


# ===== SYD DONE6 6-Continent (DOH->NBO->LHR Africa route) =====


class TestSYD6Continent:
    FIXTURE = "karryon_syd_6cont.yaml"

    def test_full_validation_passes(self):
        itin = _load(self.FIXTURE)
        report = Validator().validate(itin)
        assert report.passed, (
            f"SYD 6-continent routing should pass but got violations: "
            f"{[v.message for v in report.violations]}"
        )

    def test_6_continents_visited(self):
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        visited = set(ctx.continents_visited)
        assert visited == {
            Continent.SWP,
            Continent.ASIA,
            Continent.EU_ME,
            Continent.AFRICA,
            Continent.N_AMERICA,
            Continent.S_AMERICA,
        }

    def test_eu_me_africa_exception_applied(self):
        """EU/ME has 2 IC arrivals + 2 IC departures - needs Africa exception."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        # EU_ME IC arrivals: DOH(from DEL) and LHR(from NBO) = 2? No...
        # DEL->DOH: IC arr EU_ME #1
        # NBO->LHR: IC arr EU_ME #2
        assert ctx.intercontinental_arrivals.get(Continent.EU_ME, 0) == 2
        # DOH->NBO: IC dep EU_ME #1
        # MAD->JFK: IC dep EU_ME #2
        assert ctx.intercontinental_departures.get(Continent.EU_ME, 0) == 2

    def test_africa_visited(self):
        """NBO (Nairobi) is in Africa - confirms EU/ME exception triggers."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        assert Continent.AFRICA in ctx.continents_visited

    def test_same_tc_intercontinental(self):
        """DOH->NBO and NBO->LHR are both TC2 but intercontinental."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        # DOH(EU_ME)->NBO(Africa): both TC2, but IS intercontinental
        assert ctx.is_intercontinental[3] is True  # DOH->NBO
        # NBO(Africa)->LHR(EU_ME): both TC2, but IS intercontinental
        assert ctx.is_intercontinental[4] is True  # NBO->LHR
        # MIA(N_Am)->SCL(S_Am): both TC1, but IS intercontinental
        assert ctx.is_intercontinental[8] is True  # MIA->SCL


# ===== HND AONE3 First Class Eastbound (surface sector, 6 NA segments) =====


class TestHNDFirstClass:
    FIXTURE = "flyertalk_hnd_first.yaml"

    def test_full_validation_passes(self):
        itin = _load(self.FIXTURE)
        report = Validator().validate(itin)
        assert report.passed, (
            f"HND first class routing should pass but got violations: "
            f"{[v.message for v in report.violations]}"
        )

    def test_first_class_ticket_type(self):
        itin = _load(self.FIXTURE)
        assert itin.ticket.type.value == "AONE3"
        assert itin.ticket.cabin.value == "first"

    def test_3_continents_visited(self):
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        visited = set(ctx.continents_visited)
        assert visited == {Continent.ASIA, Continent.N_AMERICA, Continent.EU_ME}

    def test_na_at_6_segment_limit(self):
        """N_America has exactly 6 intra-continental segments (at the limit)."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        assert ctx.segments_per_continent.get(Continent.N_AMERICA, 0) == 6

    def test_surface_sector_counted(self):
        """JFK->PHL surface sector is intra-continental and counted."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        # Segment 4 (0-indexed) is JFK->PHL surface
        assert itin.segments[4].is_surface
        assert ctx.is_intercontinental[4] is False

    def test_eastbound_direction(self):
        """TC3->TC1->TC2->TC3 = eastbound."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        # HND(TC3)->SFO(TC1): TC3->TC1
        # MIA(TC1)->LHR(TC2): TC1->TC2
        # LHR(TC2)->HKG(TC3): TC2->TC3
        assert len(ctx.tc_sequence) == 4
        from rtw.models import TariffConference as TC
        assert ctx.tc_sequence == [TC.TC3, TC.TC1, TC.TC2, TC.TC3]


# ===== LHR DONE4 Eastbound (official oneworld sample) =====


class TestLHREastbound:
    FIXTURE = "oneworld_lhr_eastbound.yaml"

    def test_full_validation_passes(self):
        itin = _load(self.FIXTURE)
        report = Validator().validate(itin)
        assert report.passed, (
            f"LHR routing should pass but got violations: "
            f"{[v.message for v in report.violations]}"
        )

    def test_4_continents_visited(self):
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        visited = set(ctx.continents_visited)
        assert visited == {
            Continent.EU_ME,
            Continent.ASIA,
            Continent.SWP,
            Continent.N_AMERICA,
        }

    def test_clean_intercontinental_1_each(self):
        """Each continent has exactly 1 IC arrival and 1 IC departure."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        for cont in [Continent.EU_ME, Continent.ASIA, Continent.SWP, Continent.N_AMERICA]:
            assert ctx.intercontinental_arrivals.get(cont, 0) <= 1, (
                f"{cont.value} has {ctx.intercontinental_arrivals.get(cont, 0)} IC arrivals"
            )
            assert ctx.intercontinental_departures.get(cont, 0) <= 1, (
                f"{cont.value} has {ctx.intercontinental_departures.get(cont, 0)} IC departures"
            )

    def test_eastbound_direction(self):
        """TC2->TC3->TC1->TC2 = eastbound."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        from rtw.models import TariffConference as TC
        assert ctx.tc_sequence == [TC.TC2, TC.TC3, TC.TC1, TC.TC2]


# ===== OSL DONE4 Eastbound (intra-continent backtracking) =====


class TestOSLEastbound:
    FIXTURE = "flyertalk_osl_eastbound.yaml"

    def test_full_validation_passes(self):
        itin = _load(self.FIXTURE)
        report = Validator().validate(itin)
        assert report.passed, (
            f"OSL routing should pass but got violations: "
            f"{[v.message for v in report.violations]}"
        )

    def test_14_segments(self):
        itin = _load(self.FIXTURE)
        assert len(itin.segments) == 14

    def test_4_continents_visited(self):
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        visited = set(ctx.continents_visited)
        assert visited == {
            Continent.EU_ME,
            Continent.ASIA,
            Continent.SWP,
            Continent.N_AMERICA,
        }

    def test_intra_asia_backtrack(self):
        """HKG->HAN->HKG is allowed backtracking within Asia."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        # Segments 2,3 (HKG->HAN, HAN->HKG) are both intra-Asia
        assert ctx.is_intercontinental[2] is False  # HKG->HAN
        assert ctx.is_intercontinental[3] is False  # HAN->HKG
        assert ctx.segments_per_continent.get(Continent.ASIA, 0) == 2

    def test_intra_swp_backtrack(self):
        """SYD->PER->ADL->SYD is allowed backtracking within SWP."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        assert ctx.segments_per_continent.get(Continent.SWP, 0) == 3

    def test_eastbound_direction(self):
        """TC2->TC3->TC1->TC2 = eastbound."""
        itin = _load(self.FIXTURE)
        ctx = build_context(itin)
        from rtw.models import TariffConference as TC
        assert ctx.tc_sequence == [TC.TC2, TC.TC3, TC.TC1, TC.TC2]
