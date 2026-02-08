"""Tests for rtw.distance module."""

import pytest
from rtw.distance import DistanceCalculator


@pytest.fixture
def calc():
    return DistanceCalculator()


class TestDistanceCalculator:
    """Known-distance and edge-case tests."""

    def test_doh_nrt(self, calc):
        """DOH to NRT should be ~5,183 miles."""
        assert calc.miles("DOH", "NRT") == pytest.approx(5183, rel=0.02)

    def test_nan_sfo(self, calc):
        """NAN to SFO should be ~5,524 miles."""
        assert calc.miles("NAN", "SFO") == pytest.approx(5524, rel=0.02)

    def test_cai_amm_short_haul(self, calc):
        """CAI to AMM should be ~294 miles (short haul, wider tolerance)."""
        assert calc.miles("CAI", "AMM") == pytest.approx(294, rel=0.05)

    def test_unknown_origin(self, calc):
        """Unknown origin airport returns 0.0."""
        assert calc.miles("ZZZ", "NRT") == 0.0

    def test_unknown_dest(self, calc):
        """Unknown destination airport returns 0.0."""
        assert calc.miles("DOH", "ZZZ") == 0.0

    def test_both_unknown(self, calc):
        """Both airports unknown returns 0.0."""
        assert calc.miles("ZZZ", "XXX") == 0.0

    def test_same_airport(self, calc):
        """Same origin and destination returns 0.0."""
        assert calc.miles("DOH", "DOH") == 0.0

    def test_case_insensitive(self, calc):
        """Airport codes should be case-insensitive."""
        assert calc.miles("doh", "nrt") == pytest.approx(5183, rel=0.02)

    def test_symmetry(self, calc):
        """Distance should be the same in both directions."""
        assert calc.miles("DOH", "NRT") == calc.miles("NRT", "DOH")
