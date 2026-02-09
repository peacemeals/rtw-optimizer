"""Route generation algorithm for RTW itinerary search.

Generates valid oneworld Explorer itinerary skeletons by:
1. Grouping must-visit cities by tariff conference
2. Determining TC traversal order (eastbound/westbound)
3. Permuting cities within TC slots
4. Inserting hub connections between TCs
5. Validating each candidate through the rule engine
"""

from __future__ import annotations

import itertools
import logging
from typing import Optional

from rtw.continents import get_continent
from rtw.models import (
    CONTINENT_TO_TC,
    CabinClass,
    Continent,
    Itinerary,
    Segment,
    SegmentType,
    TariffConference,
    Ticket,
)
from rtw.search.hubs import HubTable
from rtw.search.models import CandidateItinerary, Direction, RouteSegment, SearchQuery
from rtw.validator import Validator

logger = logging.getLogger(__name__)

_MAX_CANDIDATES_PER_DIRECTION = 1000

# TC traversal orders by origin TC
_EASTBOUND_ORDERS = {
    TariffConference.TC1: [TariffConference.TC1, TariffConference.TC2, TariffConference.TC3, TariffConference.TC1],
    TariffConference.TC2: [TariffConference.TC2, TariffConference.TC3, TariffConference.TC1, TariffConference.TC2],
    TariffConference.TC3: [TariffConference.TC3, TariffConference.TC1, TariffConference.TC2, TariffConference.TC3],
}

_WESTBOUND_ORDERS = {
    TariffConference.TC1: [TariffConference.TC1, TariffConference.TC3, TariffConference.TC2, TariffConference.TC1],
    TariffConference.TC2: [TariffConference.TC2, TariffConference.TC1, TariffConference.TC3, TariffConference.TC2],
    TariffConference.TC3: [TariffConference.TC3, TariffConference.TC2, TariffConference.TC1, TariffConference.TC3],
}


def _get_tc(airport: str) -> Optional[TariffConference]:
    """Get tariff conference for an airport."""
    cont = get_continent(airport)
    if cont:
        return CONTINENT_TO_TC[cont]
    return None


def _group_cities_by_tc(
    cities: list[str],
) -> dict[TariffConference, list[str]]:
    """Group cities by their tariff conference."""
    groups: dict[TariffConference, list[str]] = {
        TariffConference.TC1: [],
        TariffConference.TC2: [],
        TariffConference.TC3: [],
    }
    for city in cities:
        tc = _get_tc(city)
        if tc:
            groups[tc].append(city)
    return groups


def _build_route(
    origin: str,
    tc_order: list[TariffConference],
    city_groups: dict[TariffConference, list[str]],
    city_permutation: dict[TariffConference, tuple[str, ...]],
    hub_table: HubTable,
) -> Optional[tuple[list[str], int]]:
    """Build a connected route from origin through TC order.

    Returns (airport_sequence, hub_count) or None if no valid connection exists.
    """
    route = [origin]
    hub_count = 0

    # Build the middle portion: visit TCs in order
    # tc_order is like [TC2, TC3, TC1, TC2] — skip first (origin TC) and last (return TC)
    middle_tcs = tc_order[1:-1]

    for tc in middle_tcs:
        cities_in_tc = list(city_permutation.get(tc, ()))
        if not cities_in_tc:
            # No must-visit cities in this TC — pick a hub to transit through
            prev_airport = route[-1]
            prev_tc = _get_tc(prev_airport)
            if prev_tc and prev_tc != tc:
                conns = hub_table.get_connections(prev_tc, tc)
                if conns:
                    # Use the best hub as a transit city
                    cities_in_tc = [conns[0].to_hub]
                    hub_count += 1
                else:
                    return None  # No connection available

        for city in cities_in_tc:
            prev_airport = route[-1]
            prev_tc = _get_tc(prev_airport)
            city_tc = _get_tc(city)

            if prev_tc and city_tc and prev_tc != city_tc:
                # Need an intercontinental connection
                conns = hub_table.get_connections(prev_tc, city_tc)
                if not conns:
                    return None

                best = conns[0]
                # If prev_airport isn't the hub, route through the hub
                if prev_airport != best.from_hub:
                    route.append(best.from_hub)
                if city != best.to_hub:
                    route.append(best.to_hub)
                    hub_count += 1
                route.append(city)
            else:
                route.append(city)

    # Return to origin
    last_airport = route[-1]
    last_tc = _get_tc(last_airport)
    origin_tc = _get_tc(origin)
    if last_tc and origin_tc and last_tc != origin_tc:
        conns = hub_table.get_connections(last_tc, origin_tc)
        if not conns:
            return None
        best = conns[0]
        if last_airport != best.from_hub:
            route.append(best.from_hub)
        if origin != best.to_hub:
            route.append(best.to_hub)
    route.append(origin)

    return route, hub_count


def _route_to_itinerary(
    route: list[str],
    query: SearchQuery,
    hub_table: HubTable,
) -> Itinerary:
    """Convert an airport sequence to an Itinerary model."""
    segments = []
    for i in range(len(route) - 1):
        from_apt = route[i]
        to_apt = route[i + 1]
        from_cont = get_continent(from_apt)
        to_cont = get_continent(to_apt)

        # Pick carrier based on whether segment is intercontinental
        if from_cont and to_cont and from_cont != to_cont:
            from_tc = CONTINENT_TO_TC[from_cont]
            to_tc = CONTINENT_TO_TC[to_cont]
            conns = hub_table.get_connections(from_tc, to_tc)
            carrier = "AA"  # fallback
            for c in conns:
                if c.from_hub == from_apt or c.to_hub == to_apt:
                    carrier = c.carrier
                    break
        else:
            # Intra-continent — use primary carrier
            cont = to_cont or from_cont
            if cont:
                carrier = hub_table.get_intra_carrier(cont)
            else:
                carrier = "AA"

        seg_type = SegmentType.STOPOVER
        # Last segment is stopover (returning to origin)
        segments.append(
            Segment(
                **{
                    "from": from_apt,
                    "to": to_apt,
                    "carrier": carrier,
                    "type": seg_type,
                }
            )
        )

    ticket = Ticket(
        type=query.ticket_type,
        cabin=query.cabin,
        origin=query.origin,
        passengers=1,
    )

    return Itinerary(ticket=ticket, segments=segments)


def _route_key(route: list[str]) -> str:
    """Create a dedup key from airport sequence."""
    return "->".join(route)


def generate_candidates(
    query: SearchQuery,
    hub_table: Optional[HubTable] = None,
) -> list[CandidateItinerary]:
    """Generate valid RTW itinerary candidates.

    Produces candidates in both eastbound and westbound directions.
    Every returned candidate passes Validator().validate() with 0 violations.

    Args:
        query: Validated search query.
        hub_table: Hub connection table (loads default if None).

    Returns:
        List of valid CandidateItinerary objects, capped at 2000 total.
    """
    if hub_table is None:
        hub_table = HubTable()

    validator = Validator()
    origin_tc = _get_tc(query.origin)
    if origin_tc is None:
        logger.warning("Unknown origin airport TC: %s", query.origin)
        return []

    # Group must-visit cities by TC
    city_groups = _group_cities_by_tc(query.cities)

    # Remove origin from cities if present (it's always start/end)
    for tc_key in city_groups:
        city_groups[tc_key] = [c for c in city_groups[tc_key] if c != query.origin]

    candidates: list[CandidateItinerary] = []
    seen_routes: set[str] = set()

    for direction, tc_orders in [
        (Direction.EASTBOUND, _EASTBOUND_ORDERS),
        (Direction.WESTBOUND, _WESTBOUND_ORDERS),
    ]:
        tc_order = tc_orders[origin_tc]
        direction_count = 0

        # Generate permutations for each TC group
        tc_perms: dict[TariffConference, list[tuple[str, ...]]] = {}
        for tc, cities in city_groups.items():
            if cities:
                tc_perms[tc] = list(itertools.permutations(cities))
            else:
                tc_perms[tc] = [()]

        # Iterate over all combinations of permutations across TCs
        for perm_combo in itertools.product(
            tc_perms[TariffConference.TC1],
            tc_perms[TariffConference.TC2],
            tc_perms[TariffConference.TC3],
        ):
            if direction_count >= _MAX_CANDIDATES_PER_DIRECTION:
                break

            perm_map = {
                TariffConference.TC1: perm_combo[0],
                TariffConference.TC2: perm_combo[1],
                TariffConference.TC3: perm_combo[2],
            }

            result = _build_route(query.origin, tc_order, city_groups, perm_map, hub_table)
            if result is None:
                continue

            route, hub_count = result

            # Dedup
            key = _route_key(route)
            if key in seen_routes:
                continue
            seen_routes.add(key)

            # Build itinerary and validate
            try:
                itinerary = _route_to_itinerary(route, query, hub_table)
            except Exception:
                logger.debug("Failed to build itinerary for route %s", route)
                continue

            report = validator.validate(itinerary)
            if not report.passed:
                continue

            # Build route segments for display
            route_segments = [
                RouteSegment(
                    from_airport=seg.from_airport,
                    to_airport=seg.to_airport,
                    carrier=seg.carrier or "AA",
                    segment_type=seg.type,
                )
                for seg in itinerary.segments
            ]

            candidates.append(
                CandidateItinerary(
                    itinerary=itinerary,
                    direction=direction,
                    route_segments=route_segments,
                    hub_count=hub_count,
                    must_visit_cities=list(query.cities),
                )
            )
            direction_count += 1

    return candidates
