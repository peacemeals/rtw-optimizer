"""Airport-to-continent classification using IATA Tariff Conferences."""

from pathlib import Path
from typing import Optional

import yaml

try:
    import airportsdata

    _airports_db = airportsdata.load("IATA")
except Exception:
    _airports_db = {}

from rtw.models import Continent, TariffConference, CONTINENT_TO_TC

_DATA_DIR = Path(__file__).parent / "data"

# Load continent data
with open(_DATA_DIR / "continents.yaml") as f:
    _CONTINENT_DATA = yaml.safe_load(f)

_OVERRIDES: dict[str, str] = _CONTINENT_DATA.get("overrides", {})
_COUNTRIES: dict[str, list[str]] = _CONTINENT_DATA.get("countries", {})
_SEGMENT_LIMITS: dict[str, int] = _CONTINENT_DATA.get("segment_limits", {})

# Build reverse country lookup: country_code -> continent_name
_COUNTRY_TO_CONTINENT: dict[str, str] = {}
for continent_name, country_codes in _COUNTRIES.items():
    for cc in country_codes:
        _COUNTRY_TO_CONTINENT[cc] = continent_name

# Load same-city groups
with open(_DATA_DIR / "same_cities.yaml") as f:
    _SAME_CITIES: dict[str, list[str]] = yaml.safe_load(f)

# Build reverse lookup: airport -> city group
_AIRPORT_TO_CITY_GROUP: dict[str, str] = {}
for group_name, airports in _SAME_CITIES.items():
    for apt in airports:
        _AIRPORT_TO_CITY_GROUP[apt] = group_name


def get_continent(airport_code: str) -> Optional[Continent]:
    """Get the continent for an airport code.

    Resolution order:
    1. Explicit overrides (CAI -> EU_ME, GUM -> Asia, etc.)
    2. Country lookup via airportsdata
    3. None if unknown
    """
    code = airport_code.upper()

    # Check overrides first
    if code in _OVERRIDES:
        return Continent(_OVERRIDES[code])

    # Try airportsdata country lookup
    if code in _airports_db:
        country = _airports_db[code].get("country", "")
        # airportsdata uses ISO 2-letter country codes
        if country in _COUNTRY_TO_CONTINENT:
            return Continent(_COUNTRY_TO_CONTINENT[country])

    return None


def get_tariff_conference(continent: Continent) -> TariffConference:
    """Get the Tariff Conference for a continent."""
    return CONTINENT_TO_TC[continent]


def get_segment_limit(continent: Continent) -> int:
    """Get the per-continent segment limit."""
    return _SEGMENT_LIMITS.get(continent.value, 4)


def get_same_city_group(airport_code: str) -> Optional[str]:
    """Get the same-city group for an airport, or None."""
    return _AIRPORT_TO_CITY_GROUP.get(airport_code.upper())


def are_same_city(airport1: str, airport2: str) -> bool:
    """Check if two airports are in the same city group."""
    g1 = get_same_city_group(airport1)
    g2 = get_same_city_group(airport2)
    if g1 is None or g2 is None:
        return airport1.upper() == airport2.upper()
    return g1 == g2
