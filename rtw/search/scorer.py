"""Scoring and ranking for RTW itinerary candidates."""

from __future__ import annotations

from rtw.search.models import AvailabilityStatus, CandidateItinerary, ScoredCandidate

# Low-YQ carriers get a bonus
_LOW_YQ_CARRIERS = {"JL", "AY", "FJ", "MH"}

# Weight presets: (availability, quality, cost)
_WEIGHT_PRESETS = {
    "availability": (0.50, 0.30, 0.20),
    "cost": (0.20, 0.20, 0.60),
    "quality": (0.15, 0.60, 0.25),
}


def availability_score(candidate: ScoredCandidate) -> float:
    """Score 0-100 based on % of flown segments with confirmed availability.

    NOT_CHECKED defaults to 50 (neutral). Surface segments excluded.
    """
    segments = candidate.candidate.itinerary.segments
    flown = [s for s in segments if s.is_flown]
    if not flown:
        return 50.0

    route_segs = candidate.candidate.route_segments
    confirmed = 0
    total = 0
    has_any_checked = False

    for i, seg in enumerate(flown):
        total += 1
        if i < len(route_segs) and route_segs[i].availability:
            status = route_segs[i].availability.status
            if status == AvailabilityStatus.NOT_CHECKED:
                continue  # Don't count in either direction
            has_any_checked = True
            if status == AvailabilityStatus.AVAILABLE:
                confirmed += 1
            elif status == AvailabilityStatus.LIKELY:
                confirmed += 0.7

    if not has_any_checked:
        return 50.0  # All NOT_CHECKED → neutral

    return min(100.0, max(0.0, (confirmed / total) * 100))


def route_quality_score(candidate: ScoredCandidate) -> float:
    """Score 0-100 based on route quality.

    Starts at 100, deductions for:
    - -8 per hub connection
    - -5 per segment beyond 12
    Bonuses:
    - +3 per segment on a low-YQ carrier
    """
    score = 100.0

    # Hub penalty
    score -= candidate.candidate.hub_count * 8

    # Segment penalty (beyond 12)
    seg_count = len(candidate.candidate.itinerary.segments)
    if seg_count > 12:
        score -= (seg_count - 12) * 5

    # Low-YQ carrier bonus
    for seg in candidate.candidate.itinerary.segments:
        if seg.carrier and seg.carrier in _LOW_YQ_CARRIERS:
            score += 3

    return min(100.0, max(0.0, score))


def cost_score(candidate: ScoredCandidate, all_candidates: list[ScoredCandidate]) -> float:
    """Score 0-100 inversely proportional to cost relative to others.

    Cheapest=100, most expensive=0. Single or equal costs=50.
    """
    if len(all_candidates) <= 1:
        return 50.0

    costs = [c.estimated_cost_usd for c in all_candidates]
    min_cost = min(costs)
    max_cost = max(costs)

    if max_cost == min_cost:
        return 50.0

    my_cost = candidate.estimated_cost_usd
    return max(0.0, min(100.0, 100.0 * (1 - (my_cost - min_cost) / (max_cost - min_cost))))


def score_candidates(
    candidates: list[ScoredCandidate],
    rank_by: str = "availability",
) -> list[ScoredCandidate]:
    """Compute composite scores using weight presets."""
    weights = _WEIGHT_PRESETS.get(rank_by, _WEIGHT_PRESETS["availability"])

    for c in candidates:
        c.availability_score = availability_score(c)
        c.quality_score = route_quality_score(c)
        c.cost_score = cost_score(c, candidates)
        c.composite_score = (
            weights[0] * c.availability_score
            + weights[1] * c.quality_score
            + weights[2] * c.cost_score
        )

    return candidates


def rank_candidates(
    scored: list[ScoredCandidate],
    top_n: int | None = None,
) -> list[ScoredCandidate]:
    """Sort by composite score descending (stable). Apply top_n limit."""
    # Stable sort: equal scores keep original order
    ranked = sorted(scored, key=lambda c: c.composite_score, reverse=True)

    for i, c in enumerate(ranked):
        c.rank = i + 1

    if top_n is not None and top_n > 0:
        ranked = ranked[:top_n]

    return ranked
