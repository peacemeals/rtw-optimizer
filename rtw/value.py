"""Segment value analyzer for RTW itineraries.

Estimates one-way business class cost per segment using great-circle
distance as a proxy, then classifies each segment's value.
"""

from rtw.distance import DistanceCalculator
from rtw.models import Itinerary, SegmentValue

# Cost heuristic constants
_BASE_RATE_PER_MILE = 0.30
_ULTRA_LONG_HAUL_THRESHOLD = 5000  # miles
_SHORT_HAUL_THRESHOLD = 500  # miles
_ULTRA_LONG_HAUL_MULTIPLIER = 1.2
_SHORT_HAUL_MULTIPLIER = 0.8

# Value classification thresholds (USD)
_EXCELLENT_THRESHOLD = 1500
_GOOD_THRESHOLD = 500
_MODERATE_THRESHOLD = 250


def _classify(cost: float) -> tuple[str, str]:
    """Return (verdict, suggestion) for an estimated J cost."""
    if cost >= _EXCELLENT_THRESHOLD:
        return "Excellent", "Great value segment"
    if cost >= _GOOD_THRESHOLD:
        return "Good", "Solid value segment"
    if cost >= _MODERATE_THRESHOLD:
        return "Moderate", "Acceptable value"
    return "Low", "Consider side trip to maximize value"


class SegmentValueAnalyzer:
    """Analyze per-segment value of a RTW itinerary."""

    def __init__(self) -> None:
        self._distance_calc = DistanceCalculator()

    def analyze(self, itinerary: Itinerary) -> list[SegmentValue]:
        """Return a SegmentValue for every segment in the itinerary."""
        results: list[SegmentValue] = []

        for i, seg in enumerate(itinerary.segments):
            route = f"{seg.from_airport}-{seg.to_airport}"
            carrier = seg.carrier or "SURFACE"

            # Surface segments: $0, N/A
            if seg.is_surface:
                results.append(
                    SegmentValue(
                        segment_index=i,
                        route=route,
                        carrier=carrier,
                        estimated_j_cost_usd=0.0,
                        verdict="N/A",
                        suggestion="Surface sector",
                        source="reference",
                    )
                )
                continue

            # Calculate distance and estimate cost
            dist = self._distance_calc.miles(seg.from_airport, seg.to_airport)
            cost = dist * _BASE_RATE_PER_MILE

            if dist > _ULTRA_LONG_HAUL_THRESHOLD:
                cost *= _ULTRA_LONG_HAUL_MULTIPLIER
            elif dist < _SHORT_HAUL_THRESHOLD:
                cost *= _SHORT_HAUL_MULTIPLIER

            cost = round(cost, 2)
            verdict, suggestion = _classify(cost)

            results.append(
                SegmentValue(
                    segment_index=i,
                    route=route,
                    carrier=carrier,
                    estimated_j_cost_usd=cost,
                    verdict=verdict,
                    suggestion=suggestion,
                    source="reference",
                )
            )

        return results
