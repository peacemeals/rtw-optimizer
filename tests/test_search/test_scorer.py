"""Tests for scoring and ranking."""

from datetime import date, timedelta

import pytest

from rtw.models import (
    CabinClass,
    Itinerary,
    Segment,
    SegmentType,
    Ticket,
    TicketType,
)
from rtw.search.models import (
    AvailabilityStatus,
    CandidateItinerary,
    Direction,
    RouteSegment,
    ScoredCandidate,
    SegmentAvailability,
)
from rtw.search.scorer import (
    availability_score,
    cost_score,
    rank_candidates,
    route_quality_score,
    score_candidates,
)


def _make_scored(
    num_segments=5,
    hub_count=0,
    carriers=None,
    avail_statuses=None,
    cost=0.0,
) -> ScoredCandidate:
    """Helper to create ScoredCandidate for testing."""
    if carriers is None:
        carriers = ["AA"] * num_segments

    segs = [
        Segment(**{"from": "AAA", "to": "BBB", "carrier": carriers[i % len(carriers)], "type": "stopover"})
        for i in range(num_segments)
    ]
    itin = Itinerary(
        ticket=Ticket(type=TicketType.DONE4, cabin=CabinClass.BUSINESS, origin="AAA"),
        segments=segs,
    )

    route_segs = []
    for i in range(num_segments):
        avail = None
        if avail_statuses and i < len(avail_statuses):
            avail = SegmentAvailability(status=avail_statuses[i])
        route_segs.append(
            RouteSegment(
                from_airport="AAA",
                to_airport="BBB",
                carrier=carriers[i % len(carriers)],
                availability=avail,
            )
        )

    candidate = CandidateItinerary(
        itinerary=itin,
        direction=Direction.EASTBOUND,
        route_segments=route_segs,
        hub_count=hub_count,
    )

    return ScoredCandidate(candidate=candidate, estimated_cost_usd=cost)


class TestAvailabilityScore:
    def test_all_available_is_100(self):
        s = _make_scored(avail_statuses=[AvailabilityStatus.AVAILABLE] * 5)
        assert availability_score(s) == 100.0

    def test_none_available_is_0(self):
        s = _make_scored(avail_statuses=[AvailabilityStatus.NOT_AVAILABLE] * 5)
        assert availability_score(s) == 0.0

    def test_partial_available(self):
        statuses = [AvailabilityStatus.AVAILABLE] * 7 + [AvailabilityStatus.NOT_AVAILABLE] * 3
        s = _make_scored(num_segments=10, avail_statuses=statuses)
        assert availability_score(s) == 70.0

    def test_all_not_checked_is_neutral(self):
        s = _make_scored(avail_statuses=[AvailabilityStatus.NOT_CHECKED] * 5)
        assert availability_score(s) == 50.0

    def test_no_availability_data_is_neutral(self):
        s = _make_scored()
        assert availability_score(s) == 50.0


class TestRouteQualityScore:
    def test_zero_hubs_high_score(self):
        s = _make_scored(hub_count=0, num_segments=5)
        score = route_quality_score(s)
        assert score >= 90

    def test_three_hubs_penalized(self):
        s = _make_scored(hub_count=3, num_segments=5)
        base = route_quality_score(_make_scored(hub_count=0, num_segments=5))
        score = route_quality_score(s)
        assert score == base - 24

    def test_excess_segments_penalized(self):
        s = _make_scored(num_segments=15, hub_count=0)
        score = route_quality_score(s)
        base = route_quality_score(_make_scored(num_segments=12, hub_count=0))
        assert score < base

    def test_low_yq_carrier_bonus(self):
        # Use enough segments that both reach penalty zone, so bonus actually differentiates
        s_low = _make_scored(carriers=["JL"] * 14, hub_count=0, num_segments=14)
        s_high = _make_scored(carriers=["BA"] * 14, hub_count=0, num_segments=14)
        assert route_quality_score(s_low) > route_quality_score(s_high)

    def test_clamped_at_zero(self):
        s = _make_scored(hub_count=15, num_segments=20)
        assert route_quality_score(s) >= 0.0

    def test_clamped_at_100(self):
        s = _make_scored(hub_count=0, num_segments=3, carriers=["JL"] * 3)
        assert route_quality_score(s) <= 100.0


class TestCostScore:
    def test_cheapest_is_100(self):
        c1 = _make_scored(cost=1000)
        c2 = _make_scored(cost=5000)
        assert cost_score(c1, [c1, c2]) == 100.0

    def test_most_expensive_is_0(self):
        c1 = _make_scored(cost=1000)
        c2 = _make_scored(cost=5000)
        assert cost_score(c2, [c1, c2]) == 0.0

    def test_equal_costs_is_50(self):
        c1 = _make_scored(cost=3000)
        c2 = _make_scored(cost=3000)
        assert cost_score(c1, [c1, c2]) == 50.0

    def test_single_candidate_is_50(self):
        c1 = _make_scored(cost=3000)
        assert cost_score(c1, [c1]) == 50.0


class TestCompositeAndRanking:
    def test_availability_weights(self):
        candidates = [_make_scored(), _make_scored()]
        scored = score_candidates(candidates, rank_by="availability")
        # Just verify it runs without error
        assert all(0 <= c.composite_score <= 100 for c in scored)

    def test_ranking_descending(self):
        candidates = [_make_scored(cost=i * 1000) for i in range(5)]
        scored = score_candidates(candidates, rank_by="cost")
        ranked = rank_candidates(scored)
        scores = [c.composite_score for c in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_limits_output(self):
        candidates = [_make_scored() for _ in range(10)]
        scored = score_candidates(candidates)
        ranked = rank_candidates(scored, top_n=3)
        assert len(ranked) == 3

    def test_empty_candidates_returns_empty(self):
        ranked = rank_candidates([], top_n=5)
        assert ranked == []

    def test_rank_numbers_assigned(self):
        candidates = [_make_scored() for _ in range(3)]
        scored = score_candidates(candidates)
        ranked = rank_candidates(scored)
        ranks = [c.rank for c in ranked]
        assert ranks == [1, 2, 3]
