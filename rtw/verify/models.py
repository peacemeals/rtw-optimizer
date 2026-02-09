"""Pydantic models for D-class verification results."""

import datetime
from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel, Field


class DClassStatus(str, Enum):
    """Status of a D-class availability check."""

    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    UNKNOWN = "unknown"
    ERROR = "error"
    CACHED = "cached"


class AlternateDateResult(BaseModel):
    """D-class availability on an alternate date (±3 days)."""

    date: datetime.date
    seats: int = Field(ge=0, le=9)
    offset_days: int = Field(ge=-3, le=3)


class FlightAvailability(BaseModel):
    """D-class availability for a single flight."""

    carrier: Optional[str] = None
    flight_number: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    depart_time: Optional[str] = None
    arrive_time: Optional[str] = None
    aircraft: Optional[str] = None
    seats: int = Field(default=0, ge=0, le=9)
    booking_class: str = "D"
    stops: int = Field(default=0, ge=0)


class DClassResult(BaseModel):
    """Result of an availability check for a single flight segment."""

    status: DClassStatus
    seats: int = Field(default=0, ge=0, le=9)
    flight_number: Optional[str] = None
    carrier: str
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    target_date: datetime.date
    booking_class: str = "D"
    checked_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    from_cache: bool = False
    error_message: Optional[str] = None
    alternate_dates: list[AlternateDateResult] = Field(default_factory=list)
    flights: list[FlightAvailability] = Field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.status == DClassStatus.AVAILABLE and self.seats > 0

    @property
    def available_flights(self) -> list[FlightAvailability]:
        """Flights with seats > 0, sorted by seats desc then departure."""
        avail = [f for f in self.flights if f.seats > 0]
        return sorted(avail, key=lambda f: (-f.seats, f.depart_time or ""))

    @property
    def flight_count(self) -> int:
        return len(self.flights)

    @property
    def available_count(self) -> int:
        return len(self.available_flights)

    @property
    def display_code(self) -> str:
        """Short display code: H9 (3 avl), D0, D?, H!"""
        bc = self.booking_class
        if self.status == DClassStatus.ERROR:
            return f"{bc}!"
        if self.status == DClassStatus.UNKNOWN:
            return f"{bc}?"
        if self.flights:
            return f"{bc}{self.seats} ({self.available_count} avl)"
        return f"{bc}{self.seats}"

    @property
    def best_alternate(self) -> Optional[AlternateDateResult]:
        """Best alternate date with highest seat count, or None."""
        available = [a for a in self.alternate_dates if a.seats > 0]
        if not available:
            return None
        return max(available, key=lambda a: (a.seats, -abs(a.offset_days)))


class SegmentVerification(BaseModel):
    """Verification result for one segment of an itinerary."""

    index: int
    segment_type: str  # FLOWN, SURFACE, TRANSIT
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    carrier: Optional[str] = None
    flight_number: Optional[str] = None
    target_date: Optional[datetime.date] = None
    dclass: Optional[DClassResult] = None


class VerifyOption(BaseModel):
    """An itinerary option to verify D-class for."""

    option_id: int
    segments: list[SegmentVerification] = Field(default_factory=list)


class VerifyResult(BaseModel):
    """Complete D-class verification result for one itinerary option."""

    option_id: int
    segments: list[SegmentVerification] = Field(default_factory=list)

    @property
    def flown_segments(self) -> list[SegmentVerification]:
        return [s for s in self.segments if s.segment_type == "FLOWN"]

    @property
    def confirmed(self) -> int:
        """Count of flown segments with D-class available."""
        return sum(
            1
            for s in self.flown_segments
            if s.dclass and s.dclass.status == DClassStatus.AVAILABLE
        )

    @property
    def total_flown(self) -> int:
        return len(self.flown_segments)

    @property
    def percentage(self) -> float:
        if self.total_flown == 0:
            return 0.0
        return self.confirmed / self.total_flown * 100

    @property
    def fully_bookable(self) -> bool:
        if self.total_flown == 0:
            return True  # Vacuously true
        return self.confirmed == self.total_flown


# Type alias for progress callbacks
ProgressCallback = Callable[[int, int, SegmentVerification], None]
