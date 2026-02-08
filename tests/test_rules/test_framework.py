"""Tests for rule engine framework."""

from rtw.continents import get_continent, are_same_city, get_same_city_group, get_segment_limit
from rtw.models import Continent, Itinerary
from rtw.validator import Validator, build_context


class TestContinentClassifier:
    def test_cai_is_eu_me(self):
        assert get_continent("CAI") == Continent.EU_ME

    def test_gum_is_asia(self):
        assert get_continent("GUM") == Continent.ASIA

    def test_mex_is_n_america(self):
        assert get_continent("MEX") == Continent.N_AMERICA

    def test_hnl_is_n_america(self):
        assert get_continent("HNL") == Continent.N_AMERICA

    def test_nan_is_swp(self):
        assert get_continent("NAN") == Continent.SWP

    def test_fun_is_swp(self):
        assert get_continent("FUN") == Continent.SWP

    def test_doh_is_eu_me(self):
        assert get_continent("DOH") == Continent.EU_ME

    def test_lowercase_works(self):
        assert get_continent("cai") == Continent.EU_ME


class TestSameCity:
    def test_nrt_hnd_same_city(self):
        assert are_same_city("NRT", "HND") is True

    def test_tsa_tpe_same_city(self):
        assert are_same_city("TSA", "TPE") is True

    def test_jfk_lga_same_city(self):
        assert are_same_city("JFK", "LGA") is True

    def test_different_cities(self):
        assert are_same_city("NRT", "HKG") is False

    def test_same_airport(self):
        assert are_same_city("NRT", "NRT") is True

    def test_city_group_lookup(self):
        assert get_same_city_group("NRT") == "TYO"
        assert get_same_city_group("HND") == "TYO"


class TestSegmentLimits:
    def test_na_limit_is_6(self):
        assert get_segment_limit(Continent.N_AMERICA) == 6

    def test_other_limits_are_4(self):
        assert get_segment_limit(Continent.EU_ME) == 4
        assert get_segment_limit(Continent.ASIA) == 4
        assert get_segment_limit(Continent.SWP) == 4


class TestValidationContext:
    def test_v3_context(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        ctx = build_context(itin)
        assert ctx.origin_continent == Continent.EU_ME
        assert len(ctx.continents_visited) >= 4
        assert Continent.EU_ME in ctx.continents_visited
        assert Continent.ASIA in ctx.continents_visited
        assert Continent.SWP in ctx.continents_visited
        assert Continent.N_AMERICA in ctx.continents_visited

    def test_same_city_pairs_detected(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        ctx = build_context(itin)
        # NRT->HND and TSA->TPE should be detected as same-city pairs
        assert len(ctx.same_city_pairs) >= 2


class TestValidator:
    def test_validator_creates(self):
        v = Validator()
        assert v is not None

    def test_validator_runs_without_crash(self, v3_itinerary):
        itin = Itinerary(**v3_itinerary)
        v = Validator()
        report = v.validate(itin)
        assert report is not None
        assert len(report.results) >= 0  # May be 0 with stub rules
