"""Search query parsing and validation."""

from __future__ import annotations

import difflib
from datetime import date
from typing import Optional

from rtw.models import CabinClass, TicketType
from rtw.search.models import SearchQuery

try:
    import airportsdata

    _airports_db = airportsdata.load("IATA")
except Exception:
    _airports_db = {}


def _fuzzy_suggestion(code: str) -> str:
    """Suggest close airport codes."""
    if not _airports_db:
        return ""
    matches = difflib.get_close_matches(code.upper(), list(_airports_db.keys()), n=3, cutoff=0.6)
    if matches:
        return f" Did you mean: {', '.join(matches)}?"
    return ""


def _min_continents(ticket_type: TicketType) -> int:
    """Minimum continents required for a ticket type."""
    return int(ticket_type.value[-1])


def parse_search_query(
    cities: list[str],
    origin: str,
    date_from: date,
    date_to: date,
    cabin: str = "business",
    ticket_type: str = "DONE4",
    top_n: int = 10,
    rank_by: str = "availability",
) -> SearchQuery:
    """Parse and validate search inputs into a SearchQuery.

    Raises ValueError with helpful messages for invalid inputs.
    """
    errors: list[str] = []

    # Uppercase
    cities_upper = [c.upper() for c in cities]
    origin_upper = origin.upper()

    # City count
    if len(cities_upper) < 3:
        raise ValueError(f"Search requires 3-8 airports, got {len(cities_upper)}")
    if len(cities_upper) > 8:
        raise ValueError(f"Search allows maximum 8 airports, got {len(cities_upper)}")

    # Duplicate check
    seen = set()
    for c in cities_upper:
        if c in seen:
            raise ValueError(f"Duplicate city: {c}")
        seen.add(c)

    # IATA validation
    for code in cities_upper + [origin_upper]:
        if _airports_db and code not in _airports_db:
            suggestion = _fuzzy_suggestion(code)
            raise ValueError(f"Unknown airport code: {code}.{suggestion}")

    # Date validation
    today = date.today()
    if date_from < today:
        raise ValueError(f"Start date {date_from} is in the past")
    if date_from >= date_to:
        raise ValueError(f"Start date {date_from} is after --to date {date_to}")

    # Cabin validation
    try:
        cabin_enum = CabinClass(cabin.lower())
    except ValueError:
        valid = ", ".join(c.value for c in CabinClass)
        raise ValueError(f"Invalid cabin class: {cabin}. Valid: {valid}")

    # Ticket type validation
    try:
        tt_enum = TicketType(ticket_type.upper())
    except ValueError:
        valid = ", ".join(t.value for t in TicketType)
        raise ValueError(f"Invalid ticket type: {ticket_type}. Valid: {valid}")

    # Continent coverage check
    from rtw.continents import get_continent

    continent_set = set()
    for code in cities_upper:
        cont = get_continent(code)
        if cont:
            continent_set.add(cont)

    origin_cont = get_continent(origin_upper)
    if origin_cont:
        continent_set.add(origin_cont)

    min_conts = _min_continents(tt_enum)
    if len(continent_set) < min_conts:
        cont_names = ", ".join(c.value for c in continent_set)
        raise ValueError(
            f"Insufficient continents for {tt_enum.value}: "
            f"need {min_conts}, have {len(continent_set)} ({cont_names}). "
            f"Add cities in other continents."
        )

    # Tight date window warning (not an error)
    window_days = (date_to - date_from).days
    warnings: list[str] = []
    if window_days < 30:
        warnings.append(
            f"Date window is only {window_days} days. "
            f"RTW trips typically need 30+ days."
        )

    return SearchQuery(
        cities=cities_upper,
        origin=origin_upper,
        date_from=date_from,
        date_to=date_to,
        cabin=cabin_enum,
        ticket_type=tt_enum,
        top_n=top_n,
        rank_by=rank_by,
    )
