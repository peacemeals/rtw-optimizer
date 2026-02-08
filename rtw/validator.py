"""Validator: builds context and runs all rules against an itinerary."""

from dataclasses import dataclass, field
from typing import Optional

from rtw.models import (
    Continent,
    TariffConference,
    Itinerary,
    RuleResult,
    ValidationReport,
    CONTINENT_TO_TC,
)
from rtw.continents import get_continent, are_same_city


@dataclass
class ValidationContext:
    """Pre-computed context for rule evaluation."""

    # Per-segment continent assignments
    segment_continents: list[Optional[Continent]] = field(default_factory=list)
    # Per-segment tariff conference
    segment_tcs: list[Optional[TariffConference]] = field(default_factory=list)
    # Origin continent
    origin_continent: Optional[Continent] = None
    # Origin tariff conference
    origin_tc: Optional[TariffConference] = None
    # Continents visited (ordered, unique)
    continents_visited: list[Continent] = field(default_factory=list)
    # Segment count per continent
    segments_per_continent: dict[Continent, int] = field(default_factory=dict)
    # Stopovers per continent
    stopovers_per_continent: dict[Continent, int] = field(default_factory=dict)
    # Same-city pairs resolved
    same_city_pairs: list[tuple[int, int]] = field(default_factory=list)
    # Direction (eastbound or westbound based on TC sequence)
    tc_sequence: list[TariffConference] = field(default_factory=list)
    # Per-segment intercontinental flag (from_continent != to_continent)
    is_intercontinental: list[bool] = field(default_factory=list)
    # Intercontinental arrivals per continent (key = destination continent)
    intercontinental_arrivals: dict[Continent, int] = field(default_factory=dict)
    # Intercontinental departures per continent (key = origin continent)
    intercontinental_departures: dict[Continent, int] = field(default_factory=dict)


def build_context(itinerary: Itinerary) -> ValidationContext:
    """Build validation context from an itinerary."""
    ctx = ValidationContext()

    # Resolve origin continent
    ctx.origin_continent = get_continent(itinerary.ticket.origin)
    if ctx.origin_continent:
        ctx.origin_tc = CONTINENT_TO_TC[ctx.origin_continent]

    seen_continents: list[Continent] = []
    segments_per: dict[Continent, int] = {}
    stopovers_per: dict[Continent, int] = {}
    tc_transitions: list[TariffConference] = []
    ic_arrivals: dict[Continent, int] = {}
    ic_departures: dict[Continent, int] = {}
    is_intercontinental_flags: list[bool] = []

    if ctx.origin_continent and ctx.origin_continent not in seen_continents:
        seen_continents.append(ctx.origin_continent)

    for i, seg in enumerate(itinerary.segments):
        # Determine continent from departure airport
        from_cont = get_continent(seg.from_airport)
        to_cont = get_continent(seg.to_airport)

        # Use destination continent for segment assignment
        cont = to_cont or from_cont
        ctx.segment_continents.append(cont)

        # Classify intercontinental: from_continent != to_continent
        seg_is_ic = (
            from_cont is not None
            and to_cont is not None
            and from_cont != to_cont
        )
        is_intercontinental_flags.append(seg_is_ic)

        if cont:
            tc = CONTINENT_TO_TC[cont]
            ctx.segment_tcs.append(tc)

            if seg_is_ic:
                # Intercontinental: count arrivals/departures, not per-continent
                ic_arrivals[to_cont] = ic_arrivals.get(to_cont, 0) + 1
                ic_departures[from_cont] = ic_departures.get(from_cont, 0) + 1
            else:
                # Intra-continental: count toward per-continent segment limit
                segments_per[cont] = segments_per.get(cont, 0) + 1

            # Count stopovers per continent (unchanged — by destination)
            if seg.is_stopover:
                stopovers_per[cont] = stopovers_per.get(cont, 0) + 1

            # Track continent visits
            if cont not in seen_continents:
                seen_continents.append(cont)

            # Track TC transitions (cross-TC only)
            if from_cont and to_cont and from_cont != to_cont:
                from_tc = CONTINENT_TO_TC[from_cont]
                to_tc = CONTINENT_TO_TC[to_cont]
                if from_tc != to_tc:
                    if not tc_transitions:
                        tc_transitions.append(from_tc)
                    tc_transitions.append(to_tc)
        else:
            ctx.segment_tcs.append(None)

    # Detect same-city pairs (consecutive segments where arrival airport
    # of seg N and departure airport of seg N+1 are same-city but different codes)
    for i in range(len(itinerary.segments) - 1):
        arr = itinerary.segments[i].to_airport
        dep = itinerary.segments[i + 1].from_airport
        if arr != dep and are_same_city(arr, dep):
            ctx.same_city_pairs.append((i, i + 1))

    ctx.continents_visited = seen_continents
    ctx.segments_per_continent = segments_per
    ctx.stopovers_per_continent = stopovers_per
    ctx.tc_sequence = tc_transitions
    ctx.is_intercontinental = is_intercontinental_flags
    ctx.intercontinental_arrivals = ic_arrivals
    ctx.intercontinental_departures = ic_departures

    return ctx


class Validator:
    """Runs all registered rules against an itinerary."""

    def __init__(self) -> None:
        # Import rule modules to trigger registration
        self._discover_rules()

    def _discover_rules(self) -> None:
        """Import all rule modules so @register_rule decorators fire."""
        import rtw.rules.segments  # noqa: F401
        import rtw.rules.direction  # noqa: F401
        import rtw.rules.stopovers  # noqa: F401
        import rtw.rules.surface  # noqa: F401
        import rtw.rules.geography  # noqa: F401
        import rtw.rules.carriers  # noqa: F401
        import rtw.rules.validity  # noqa: F401
        import rtw.rules.hemisphere  # noqa: F401
        import rtw.rules.intercontinental  # noqa: F401

    def validate(self, itinerary: Itinerary) -> ValidationReport:
        """Run all rules and return a validation report."""
        from rtw.rules.base import get_registered_rules

        context = build_context(itinerary)
        all_results: list[RuleResult] = []

        for rule_cls in get_registered_rules():
            rule = rule_cls()
            try:
                results = rule.check(itinerary, context)
                all_results.extend(results)
            except Exception as e:
                all_results.append(
                    RuleResult(
                        rule_id=getattr(rule, "rule_id", "unknown"),
                        rule_name=getattr(rule, "rule_name", "Unknown"),
                        passed=False,
                        message=f"Rule execution error: {e}",
                        fix_suggestion="Check rule implementation.",
                    )
                )

        return ValidationReport(itinerary=itinerary, results=all_results)
