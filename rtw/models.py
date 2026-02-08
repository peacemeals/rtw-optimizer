"""Domain models for RTW Optimizer.

Pydantic models for oneworld Explorer itineraries, validation results,
NTP estimates, cost estimates, and segment value analysis.
"""

from datetime import date as Date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --- Enums ---


class TicketType(str, Enum):
    """oneworld Explorer ticket types."""

    DONE3 = "DONE3"
    DONE4 = "DONE4"
    DONE5 = "DONE5"
    DONE6 = "DONE6"
    LONE3 = "LONE3"
    LONE4 = "LONE4"
    LONE5 = "LONE5"
    LONE6 = "LONE6"
    AONE3 = "AONE3"
    AONE4 = "AONE4"
    AONE5 = "AONE5"
    AONE6 = "AONE6"


class CabinClass(str, Enum):
    """Cabin classes."""

    ECONOMY = "economy"
    BUSINESS = "business"
    FIRST = "first"


class SegmentType(str, Enum):
    """Segment classification for stopover/transit/surface."""

    STOPOVER = "stopover"  # >24h between arrival and departure
    TRANSIT = "transit"  # <=24h between flights
    SURFACE = "surface"  # Ground transport between airports
    FINAL = "final"  # Last segment returning to origin


class Continent(str, Enum):
    """oneworld Explorer continent definitions."""

    EU_ME = "EU_ME"  # Europe / Middle East (TC2)
    AFRICA = "Africa"  # Sub-Saharan Africa (TC2)
    ASIA = "Asia"  # Asia (TC3)
    SWP = "SWP"  # South West Pacific (TC3)
    N_AMERICA = "N_America"  # North America (TC1)
    S_AMERICA = "S_America"  # South America (TC1)


class TariffConference(str, Enum):
    """IATA Tariff Conference zones."""

    TC1 = "TC1"  # Americas
    TC2 = "TC2"  # Europe, Middle East, Africa
    TC3 = "TC3"  # Asia, South West Pacific


class NTPMethod(str, Enum):
    """NTP earning method."""

    REVENUE = "revenue"  # BA, AA, IB: 1 NTP per GBP 1
    DISTANCE = "distance"  # All others: percentage of miles


class Severity(str, Enum):
    """Validation result severity."""

    VIOLATION = "violation"  # Rule broken — ticket invalid
    WARNING = "warning"  # Ambiguous or risky
    INFO = "info"  # Informational


# --- Tariff Conference Mapping ---

CONTINENT_TO_TC: dict[Continent, TariffConference] = {
    Continent.N_AMERICA: TariffConference.TC1,
    Continent.S_AMERICA: TariffConference.TC1,
    Continent.EU_ME: TariffConference.TC2,
    Continent.AFRICA: TariffConference.TC2,
    Continent.ASIA: TariffConference.TC3,
    Continent.SWP: TariffConference.TC3,
}


# --- Core Itinerary Models ---


class Ticket(BaseModel):
    """RTW ticket metadata."""

    type: TicketType
    cabin: CabinClass
    origin: str = Field(min_length=3, max_length=3, description="3-letter IATA airport code")
    passengers: int = Field(ge=1, le=9, default=1)
    departure: Optional[Date] = None
    plating_carrier: Optional[str] = Field(default=None, min_length=2, max_length=2)

    @field_validator("origin", mode="before")
    @classmethod
    def uppercase_origin(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v

    @field_validator("plating_carrier", mode="before")
    @classmethod
    def uppercase_plating(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if isinstance(v, str) else v

    @property
    def num_continents(self) -> int:
        """Number of continents from ticket type."""
        return int(self.type.value[-1])

    @property
    def fare_prefix(self) -> str:
        """Fare prefix letter (D=business, L=economy, A=first)."""
        return self.type.value[0]


class Segment(BaseModel):
    """A single flight or surface segment."""

    from_airport: str = Field(alias="from", min_length=3, max_length=3)
    to_airport: str = Field(alias="to", min_length=3, max_length=3)
    carrier: Optional[str] = Field(default=None, min_length=2, max_length=2)
    flight: Optional[str] = None
    date: Optional[Date] = None
    type: SegmentType = SegmentType.STOPOVER
    notes: Optional[str] = None

    model_config = {"populate_by_name": True}

    @field_validator("from_airport", "to_airport", mode="before")
    @classmethod
    def uppercase_airports(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v

    @field_validator("carrier", mode="before")
    @classmethod
    def uppercase_carrier(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if isinstance(v, str) else v

    @property
    def is_surface(self) -> bool:
        return self.type == SegmentType.SURFACE

    @property
    def is_stopover(self) -> bool:
        return self.type == SegmentType.STOPOVER

    @property
    def is_flown(self) -> bool:
        return self.type != SegmentType.SURFACE


class Itinerary(BaseModel):
    """Complete RTW itinerary."""

    ticket: Ticket
    segments: list[Segment] = Field(min_length=1)

    @property
    def flown_segments(self) -> list[Segment]:
        """Segments that are actually flown (excludes surface)."""
        return [s for s in self.segments if s.is_flown]

    @property
    def surface_segments(self) -> list[Segment]:
        """Surface sectors only."""
        return [s for s in self.segments if s.is_surface]

    @property
    def stopovers(self) -> list[Segment]:
        """Stopover segments only."""
        return [s for s in self.segments if s.is_stopover]


# --- Reference Data Models ---


class Airport(BaseModel):
    """Airport reference data."""

    iata: str = Field(min_length=3, max_length=3)
    name: str = ""
    city: str = ""
    country: str = ""
    continent: Optional[Continent] = None
    tariff_conference: Optional[TariffConference] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    same_city_group: Optional[str] = None


class CarrierInfo(BaseModel):
    """Carrier reference data."""

    code: str = Field(min_length=2, max_length=2)
    name: str
    alliance: str = "oneworld"
    eligible: bool = True
    ntp_method: Optional[NTPMethod] = None
    ntp_rates: Optional[dict[str, float]] = None
    yq_tier: Optional[str] = None
    yq_estimate_per_segment: Optional[float] = None
    rtw_booking_class: Optional[str] = None
    notes: str = ""


class FareReference(BaseModel):
    """Fare reference data for a specific origin."""

    origin: str = Field(min_length=3, max_length=3)
    ticket_type: TicketType
    base_fare_usd: float
    currency: str = "USD"
    last_updated: Optional[Date] = None


# --- Result Models ---


class RuleResult(BaseModel):
    """Result of a single rule check."""

    rule_id: str
    rule_name: str
    rule_reference: str = ""  # e.g. "Rule 3015 §4"
    passed: bool
    severity: Severity = Severity.VIOLATION
    message: str
    fix_suggestion: str = ""
    segments_involved: list[int] = Field(default_factory=list)


class ValidationReport(BaseModel):
    """Complete validation report for an itinerary."""

    itinerary: Itinerary
    results: list[RuleResult] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.severity == Severity.VIOLATION)

    @property
    def violations(self) -> list[RuleResult]:
        return [r for r in self.results if not r.passed and r.severity == Severity.VIOLATION]

    @property
    def warnings(self) -> list[RuleResult]:
        return [r for r in self.results if not r.passed and r.severity == Severity.WARNING]

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


class NTPEstimate(BaseModel):
    """NTP estimate for a single segment."""

    segment_index: int
    route: str  # e.g. "DOH-NRT"
    carrier: str
    distance_miles: float = 0.0
    method: NTPMethod
    rate: Optional[float] = None  # percentage for distance-based
    estimated_ntp: float = 0.0
    confidence: str = "calculated"  # "calculated" or "estimated"
    notes: str = ""


class CostEstimate(BaseModel):
    """Cost estimate for an itinerary."""

    origin: str
    ticket_type: TicketType
    base_fare_usd: float = 0.0
    total_yq_usd: float = 0.0
    total_per_person_usd: float = 0.0
    total_all_pax_usd: float = 0.0
    passengers: int = 1
    plating_carrier: str = ""
    notes: str = ""


class SegmentValue(BaseModel):
    """Value analysis for a single segment."""

    segment_index: int
    route: str
    carrier: str
    estimated_j_cost_usd: float = 0.0
    verdict: str = ""  # "Excellent", "Good", "Moderate", "Low"
    suggestion: str = ""
    source: str = "reference"  # "reference" or "scraped"
