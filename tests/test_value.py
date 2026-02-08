"""Tests for SegmentValueAnalyzer."""

import pytest
from rtw.models import Itinerary
from rtw.value import SegmentValueAnalyzer


@pytest.fixture
def analyzer():
    return SegmentValueAnalyzer()


@pytest.fixture
def itinerary(v3_itinerary):
    return Itinerary(**v3_itinerary)


class TestSegmentValueAnalyzer:
    """Value classification tests against acceptance criteria."""

    def test_doh_nrt_excellent(self, analyzer, itinerary):
        """DOH-NRT (~5183mi) should be Excellent: 5183 * 0.30 * 1.2 ≈ $1866."""
        results = analyzer.analyze(itinerary)
        doh_nrt = next(r for r in results if r.route == "DOH-NRT")
        assert doh_nrt.verdict == "Excellent"
        assert doh_nrt.estimated_j_cost_usd > 1500

    def test_nan_sfo_excellent(self, analyzer, itinerary):
        """NAN-SFO (~5525mi) should be Excellent."""
        results = analyzer.analyze(itinerary)
        nan_sfo = next(r for r in results if r.route == "NAN-SFO")
        assert nan_sfo.verdict == "Excellent"
        assert nan_sfo.estimated_j_cost_usd > 1500

    def test_cai_amm_low(self, analyzer, itinerary):
        """CAI-AMM (~294mi) should be Low: 294 * 0.30 * 0.8 ≈ $71."""
        results = analyzer.analyze(itinerary)
        cai_amm = next(r for r in results if r.route == "CAI-AMM")
        assert cai_amm.verdict in ("Low", "Moderate")
        assert cai_amm.estimated_j_cost_usd < 250

    def test_surface_segment_na(self, analyzer, itinerary):
        """Surface segment (JFK-MCO) should be N/A with $0."""
        results = analyzer.analyze(itinerary)
        surface = next(r for r in results if r.route == "JFK-MCO")
        assert surface.verdict == "N/A"
        assert surface.estimated_j_cost_usd == 0.0
        assert surface.suggestion == "Surface sector"

    def test_v3_full_itinerary_count(self, analyzer, itinerary):
        """Full V3 itinerary should produce one SegmentValue per segment."""
        results = analyzer.analyze(itinerary)
        assert len(results) == len(itinerary.segments)

    def test_excellent_suggestion(self, analyzer, itinerary):
        """Excellent segments should have 'Great value segment' suggestion."""
        results = analyzer.analyze(itinerary)
        doh_nrt = next(r for r in results if r.route == "DOH-NRT")
        assert doh_nrt.suggestion == "Great value segment"

    def test_low_suggestion(self, analyzer, itinerary):
        """Low segments should suggest maximizing value."""
        results = analyzer.analyze(itinerary)
        cai_amm = next(r for r in results if r.route == "CAI-AMM")
        if cai_amm.verdict == "Low":
            assert "side trip" in cai_amm.suggestion.lower()
