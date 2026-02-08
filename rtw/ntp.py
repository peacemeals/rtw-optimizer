"""NTP (New Tier Points) calculator for RTW itineraries.

Supports two earning methods:
- Distance-based: NTP = distance_miles * (rate_percentage / 100)
- Revenue-based: NTP = estimated GBP spend (1 NTP per GBP 1)

Rate data loaded from rtw/data/ntp_rates.yaml.
"""

from pathlib import Path
from typing import Optional

import yaml

from rtw.distance import DistanceCalculator
from rtw.models import (
    Itinerary,
    NTPEstimate,
    NTPMethod,
    Segment,
)

_DATA_DIR = Path(__file__).parent / "data"

# Rough USD-to-GBP conversion rate
_USD_TO_GBP = 0.79


class NTPCalculator:
    """Calculate NTP earnings for RTW itinerary segments."""

    def __init__(self) -> None:
        with open(_DATA_DIR / "ntp_rates.yaml") as f:
            self._rates = yaml.safe_load(f)

        with open(_DATA_DIR / "fares.yaml") as f:
            self._fares = yaml.safe_load(f)

        self._distance_calc = DistanceCalculator()

        # Build sets for quick lookup
        self._revenue_carriers = set(self._rates["revenue_based"]["carriers"])
        self._distance_carriers = set(self._rates["distance_based"].keys())
        self._ba_bonus = self._rates.get("ba_bonus", {})

    # ------------------------------------------------------------------
    # Distance-based NTP
    # ------------------------------------------------------------------

    def _distance_based(
        self,
        segment_index: int,
        segment: Segment,
        distance_miles: float,
        booking_class: str,
    ) -> NTPEstimate:
        """Calculate NTP for a distance-based carrier."""
        carrier = segment.carrier or ""
        carrier_rates = self._rates["distance_based"].get(carrier, {})
        rate = carrier_rates.get(booking_class, 0)

        ntp = distance_miles * (rate / 100)

        route = f"{segment.from_airport}-{segment.to_airport}"
        notes = ""

        # FJ ATR-72 segments: D maps to Y cabin but still earns at D-class rate
        if carrier == "FJ" and distance_miles < 700 and booking_class == "D":
            notes = "ATR-72 segment: D maps to Y cabin, earns at D-class rate"

        return NTPEstimate(
            segment_index=segment_index,
            route=route,
            carrier=carrier,
            distance_miles=distance_miles,
            method=NTPMethod.DISTANCE,
            rate=rate,
            estimated_ntp=round(ntp, 1),
            confidence="calculated",
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Revenue-based NTP
    # ------------------------------------------------------------------

    def _revenue_based(
        self,
        segment_index: int,
        segment: Segment,
        distance_miles: float,
        total_fare_usd: float,
        total_distance: float,
    ) -> NTPEstimate:
        """Calculate NTP for a revenue-based carrier.

        Uses distance-weighted fare allocation: each segment's share of the
        total fare is proportional to its share of total flown distance.
        """
        carrier = segment.carrier or ""
        route = f"{segment.from_airport}-{segment.to_airport}"

        # Allocate fare proportionally by distance
        if total_distance > 0:
            segment_share_usd = (distance_miles / total_distance) * total_fare_usd
        else:
            segment_share_usd = 0.0

        segment_share_gbp = segment_share_usd * _USD_TO_GBP
        ntp = segment_share_gbp  # 1 NTP per GBP 1

        notes_parts = [
            f"${segment_share_usd:.0f} allocated ({distance_miles:.0f}/"
            f"{total_distance:.0f} mi), ~{chr(163)}{segment_share_gbp:.0f}"
        ]

        # BA bonus NTP for Club World (long-haul business)
        bonus = 0.0
        if carrier == "BA":
            bonus = self._ba_bonus.get("club_world", 400)
            ntp += bonus
            notes_parts.append(f"+{bonus:.0f} BA Club World bonus")

        return NTPEstimate(
            segment_index=segment_index,
            route=route,
            carrier=carrier,
            distance_miles=distance_miles,
            method=NTPMethod.REVENUE,
            rate=None,
            estimated_ntp=round(ntp, 1),
            confidence="estimated",
            notes="; ".join(notes_parts),
        )

    # ------------------------------------------------------------------
    # Full itinerary calculation
    # ------------------------------------------------------------------

    def calculate(
        self,
        itinerary: Itinerary,
        booking_class: str = "D",
        total_fare_usd: Optional[float] = None,
    ) -> list[NTPEstimate]:
        """Calculate NTP for every segment in the itinerary.

        Args:
            itinerary: The parsed itinerary.
            booking_class: The booking class for distance-based calculation.
            total_fare_usd: Total fare in USD. If None, looked up from fares.yaml.

        Returns:
            List of NTPEstimate, one per segment (including 0-NTP surface sectors).
        """
        # Resolve total fare
        if total_fare_usd is None:
            total_fare_usd = self._default_fare(itinerary)

        # Pre-compute all distances
        distances: list[float] = []
        for seg in itinerary.segments:
            if seg.is_surface:
                distances.append(0.0)
            else:
                distances.append(self._distance_calc.miles(seg.from_airport, seg.to_airport))

        total_distance = sum(distances)

        # Calculate NTP per segment
        results: list[NTPEstimate] = []
        for i, seg in enumerate(itinerary.segments):
            dist = distances[i]

            # Surface segments earn zero NTP
            if seg.is_surface:
                results.append(
                    NTPEstimate(
                        segment_index=i,
                        route=f"{seg.from_airport}-{seg.to_airport}",
                        carrier=seg.carrier or "SURFACE",
                        distance_miles=0.0,
                        method=NTPMethod.DISTANCE,
                        rate=0,
                        estimated_ntp=0.0,
                        confidence="calculated",
                        notes="Surface sector — no NTP earned",
                    )
                )
                continue

            carrier = seg.carrier or ""

            if carrier in self._revenue_carriers:
                est = self._revenue_based(i, seg, dist, total_fare_usd, total_distance)
            elif carrier in self._distance_carriers:
                est = self._distance_based(i, seg, dist, booking_class)
            else:
                # Unknown carrier — attempt distance-based with 0 rate
                est = self._distance_based(i, seg, dist, booking_class)
                est.notes = f"Unknown carrier {carrier}; no NTP rate found"

            results.append(est)

        return results

    def _default_fare(self, itinerary: Itinerary) -> float:
        """Look up default fare from fares.yaml for the itinerary origin."""
        origin = itinerary.ticket.origin
        ticket_type = itinerary.ticket.type.value
        origins = self._fares.get("origins", {})

        origin_data = origins.get(origin, {})
        fares = origin_data.get("fares", {})
        fare = fares.get(ticket_type, 0)

        if fare == 0:
            # Fallback: use CAI as cheapest origin
            cai_fares = origins.get("CAI", {}).get("fares", {})
            fare = cai_fares.get(ticket_type, 4000)

        return float(fare)
