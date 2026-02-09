"""Fare comparison: RTW base fare vs individual segment prices."""

from __future__ import annotations

from pydantic import BaseModel


class FareComparison(BaseModel):
    """Comparison of RTW base fare against sum of individual segment prices."""

    base_fare_usd: float = 0.0
    segment_total_usd: float = 0.0
    segments_priced: int = 0
    segments_total: int = 0
    savings_usd: float = 0.0
    value_multiplier: float = 0.0

    @property
    def verdict(self) -> str:
        m = self.value_multiplier
        if m >= 3.0:
            return "excellent"
        if m >= 2.0:
            return "great"
        if m >= 1.5:
            return "good"
        if m >= 1.0:
            return "fair"
        return "poor"

    @property
    def is_complete(self) -> bool:
        return self.segments_priced == self.segments_total and self.segments_total > 0


def compute_fare_comparison(candidate, query) -> FareComparison:
    """Compute fare comparison for a scored candidate.

    Args:
        candidate: ScoredCandidate with route_segments populated.
        query: SearchQuery with origin and ticket_type.

    Returns:
        FareComparison with all fields populated.
    """
    from rtw.cost import CostEstimator

    estimator = CostEstimator()
    base_fare = estimator.get_base_fare(query.origin, query.ticket_type)

    segments = candidate.candidate.itinerary.segments
    route_segs = candidate.candidate.route_segments

    segment_total = 0.0
    segments_priced = 0
    segments_total = 0

    for i, seg in enumerate(segments):
        if seg.is_surface:
            continue
        segments_total += 1

        if i < len(route_segs) and route_segs[i].availability:
            price = route_segs[i].availability.price_usd
            if price is not None and price > 0:
                segment_total += price
                segments_priced += 1

    savings = segment_total - base_fare if segments_priced > 0 else 0.0
    multiplier = (
        round(segment_total / base_fare, 2)
        if base_fare > 0 and segments_priced > 0
        else 0.0
    )

    return FareComparison(
        base_fare_usd=round(base_fare, 2),
        segment_total_usd=round(segment_total, 2),
        segments_priced=segments_priced,
        segments_total=segments_total,
        savings_usd=round(savings, 2),
        value_multiplier=multiplier,
    )
