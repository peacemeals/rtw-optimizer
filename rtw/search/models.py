"""Pydantic models for the RTW search pipeline."""

import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from rtw.models import (
    CabinClass,
    Itinerary,
    SegmentType,
    TicketType,
)
from rtw.search.fare_comparison import FareComparison


class Direction(str, Enum):
    """Route direction around the globe."""

    EASTBOUND = "eastbound"
    WESTBOUND = "westbound"


class AvailabilityStatus(str, Enum):
    """Award seat availability status."""

    AVAILABLE = "available"
    LIKELY = "likely"
    UNKNOWN = "unknown"
    NOT_AVAILABLE = "not_available"
    NOT_CHECKED = "not_checked"


class SearchQuery(BaseModel):
    """User's search request."""

    cities: list[str] = Field(min_length=3, max_length=8)
    origin: str = Field(min_length=3, max_length=3)
    date_from: datetime.date
    date_to: datetime.date
    cabin: CabinClass
    ticket_type: TicketType
    top_n: int = Field(default=10, ge=1)
    rank_by: str = "availability"

    @field_validator("origin", mode="before")
    @classmethod
    def uppercase_origin(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v

    @field_validator("cities", mode="before")
    @classmethod
    def uppercase_cities(cls, v: list[str]) -> list[str]:
        return [c.upper() if isinstance(c, str) else c for c in v]

    @model_validator(mode="after")
    def dates_ordered(self) -> "SearchQuery":
        if self.date_from >= self.date_to:
            raise ValueError("date_from must be before date_to")
        return self


class SegmentAvailability(BaseModel):
    """Availability result for a single segment."""

    status: AvailabilityStatus = AvailabilityStatus.NOT_CHECKED
    price_usd: Optional[float] = None
    carrier: Optional[str] = None
    date: Optional[datetime.date] = None


class RouteSegment(BaseModel):
    """A segment in a generated route."""

    from_airport: str = Field(min_length=3, max_length=3)
    to_airport: str = Field(min_length=3, max_length=3)
    carrier: str = Field(min_length=2, max_length=2)
    segment_type: SegmentType = SegmentType.STOPOVER
    availability: Optional[SegmentAvailability] = None

    @field_validator("from_airport", "to_airport", mode="before")
    @classmethod
    def uppercase_airports(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v

    @field_validator("carrier", mode="before")
    @classmethod
    def uppercase_carrier(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v


class CandidateItinerary(BaseModel):
    """A generated RTW itinerary candidate."""

    itinerary: Itinerary
    direction: Direction
    route_segments: list[RouteSegment] = Field(default_factory=list)
    hub_count: int = 0
    must_visit_cities: list[str] = Field(default_factory=list)

    @property
    def segment_count(self) -> int:
        return len(self.itinerary.segments)


class ScoredCandidate(BaseModel):
    """A candidate itinerary with scores."""

    candidate: CandidateItinerary
    availability_score: float = 50.0
    quality_score: float = 50.0
    cost_score: float = 50.0
    composite_score: float = 50.0
    rank: int = 0
    estimated_cost_usd: float = 0.0
    availability_pct: float = 0.0
    fare_comparison: Optional["FareComparison"] = None


class SearchResult(BaseModel):
    """Complete search result."""

    query: SearchQuery
    candidates_generated: int = 0
    options: list[ScoredCandidate] = Field(default_factory=list)
    base_fare_usd: float = 0.0
