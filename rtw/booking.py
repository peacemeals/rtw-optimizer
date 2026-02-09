"""Booking script generator for oneworld Explorer RTW tickets.

Generates phone scripts (natural-language instructions for calling the airline)
and Amadeus GDS commands for booking an RTW itinerary.

Data loaded from:
- rtw/data/carriers.yaml (booking classes per carrier)
- rtw/data/same_cities.yaml (same-city airport groups for warnings)
"""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from rtw.models import CabinClass, Itinerary, SegmentType

_DATA_DIR = Path(__file__).parent / "data"


# --- Data Models ---


class SegmentScript(BaseModel):
    """Phone script and GDS entry for a single segment."""

    segment_index: int
    route: str
    carrier: Optional[str] = None
    booking_class: Optional[str] = None
    phone_instruction: str
    gds_command: str = ""
    warnings: list[str] = Field(default_factory=list)


class BookingScript(BaseModel):
    """Complete booking script with phone instructions and GDS commands."""

    opening: str
    segments: list[SegmentScript]
    closing: str
    gds_commands: list[str]
    warnings: list[str] = Field(default_factory=list)


# --- Generator ---


class BookingGenerator:
    """Generate phone scripts and GDS commands for RTW bookings."""

    def __init__(self) -> None:
        with open(_DATA_DIR / "carriers.yaml") as f:
            self._carriers: dict = yaml.safe_load(f)

        with open(_DATA_DIR / "same_cities.yaml") as f:
            self._same_cities: dict[str, list[str]] = yaml.safe_load(f)

        # Build reverse lookup: airport -> city group name
        self._airport_to_city: dict[str, str] = {}
        for group, airports in self._same_cities.items():
            for apt in airports:
                self._airport_to_city[apt] = group

    # --- Booking class logic (T031) ---

    def _get_booking_class(self, carrier: Optional[str], cabin: CabinClass) -> Optional[str]:
        """Determine the booking class for a carrier/cabin combination.

        Delegates to shared utility in rtw.carriers. Returns None for
        surface segments (carrier=None).
        """
        if carrier is None:
            return None

        from rtw.carriers import get_booking_class

        return get_booking_class(carrier, cabin)

    def _is_same_city(self, airport1: str, airport2: str) -> bool:
        """Check if two airports are in the same city group."""
        g1 = self._airport_to_city.get(airport1.upper())
        g2 = self._airport_to_city.get(airport2.upper())
        if g1 is None or g2 is None:
            return airport1.upper() == airport2.upper()
        return g1 == g2

    def _get_city_group_name(self, airport: str) -> Optional[str]:
        """Get the city group name for an airport, or None."""
        return self._airport_to_city.get(airport.upper())

    # --- Phone script (T032) ---

    def _opening_script(self, itinerary: Itinerary) -> str:
        """Generate the opening phone script."""
        t = itinerary.ticket
        cabin = t.cabin.value.title()
        pax = t.passengers
        origin = t.origin
        plating = t.plating_carrier or "AA"
        num_continents = t.num_continents
        departure = t.departure.strftime("%d %B %Y") if t.departure else "TBD"
        num_segments = len(itinerary.flown_segments)

        lines = [
            "Hello, I'd like to book a oneworld Explorer Round-the-World ticket.",
            "",
            f"  Ticket type:  {t.type.value} ({num_continents} continents, {cabin})",
            f"  Passengers:   {pax}",
            f"  Origin:       {origin}",
            f"  Departure:    {departure}",
            f"  Plating:      {plating}",
            f"  Segments:     {num_segments} flown + {len(itinerary.surface_segments)} surface",
            "",
            "I'll give you the segments one at a time. Please book each segment",
            "before we move to the next one.",
        ]
        return "\n".join(lines)

    def _segment_scripts(self, itinerary: Itinerary) -> list[SegmentScript]:
        """Generate per-segment phone instructions and warnings."""
        cabin = itinerary.ticket.cabin
        segments = itinerary.segments
        scripts: list[SegmentScript] = []

        for i, seg in enumerate(segments):
            warnings: list[str] = []
            booking_class = self._get_booking_class(seg.carrier, cabin)
            route = f"{seg.from_airport}-{seg.to_airport}"

            # --- Same-city transition warning ---
            # Check if this segment departs from a different airport in the
            # same city where the previous segment arrived
            if i > 0:
                prev = segments[i - 1]
                if prev.to_airport != seg.from_airport and self._is_same_city(
                    prev.to_airport, seg.from_airport
                ):
                    city = self._get_city_group_name(seg.from_airport)
                    warnings.append(
                        f"Same-city transition: {prev.to_airport} -> {seg.from_airport} "
                        f"({city}). Passenger must transfer between airports."
                    )

            # --- Surface segment ---
            if seg.is_surface:
                instruction = (
                    f"Segment {i + 1}: SURFACE — {route}\n"
                    f"  This is ground transport, not a booked flight.\n"
                    f"  No booking needed for this segment."
                )
                if seg.notes:
                    instruction += f"\n  Note: {seg.notes}"

                scripts.append(
                    SegmentScript(
                        segment_index=i,
                        route=route,
                        carrier=None,
                        booking_class=None,
                        phone_instruction=instruction,
                        gds_command="",
                        warnings=warnings,
                    )
                )
                continue

            # --- FJ ATR-72 note ---
            fj_atr_note = ""
            if seg.carrier == "FJ" and booking_class == "D":
                # Check notes for ATR-72 indicator
                if seg.notes and "ATR" in seg.notes.upper():
                    fj_atr_note = (
                        " (Note: ATR-72 is single class — D maps to Y. "
                        "Confirm Y class availability.)"
                    )

            # --- Married segment warning (short connection) ---
            # If this segment is a transit and connects to the next segment
            # on the same day, warn about married segment risk (airline may
            # link both flights so changing one cancels the other)
            if seg.type == SegmentType.TRANSIT and i + 1 < len(segments):
                nxt = segments[i + 1]
                if (
                    not nxt.is_surface
                    and seg.date is not None
                    and nxt.date is not None
                    and seg.date == nxt.date
                ):
                    warnings.append(
                        f"Married segment risk: {seg.from_airport}-{seg.to_airport} "
                        f"connects to {nxt.from_airport}-{nxt.to_airport} same day. "
                        f"If booked as married segment, changes to one flight may "
                        f"cancel both. Request separate PNRs if possible."
                    )

            # --- Mainline IB verification ---
            if seg.carrier == "IB":
                flight_num = seg.flight or ""
                # Iberia Express is I2, but flights may show as IB operationally
                # Flag MAD-CAI or any IB segment for verification
                if "MAD" in (seg.from_airport, seg.to_airport):
                    warnings.append(
                        f"Verify this is mainline Iberia (IB), not Iberia Express (I2). "
                        f"Flight {flight_num}: check operating carrier is IB."
                    )

            # --- Build phone instruction ---
            date_str = seg.date.strftime("%d %b %Y") if seg.date else "date TBD"
            flight_info = f" flight {seg.flight}" if seg.flight else ""

            instruction = (
                f"Segment {i + 1}: {seg.carrier}{flight_info} — {route} — {date_str}\n"
                f"  Booking class: {booking_class}"
            )
            if fj_atr_note:
                instruction += fj_atr_note
            if seg.notes:
                instruction += f"\n  Note: {seg.notes}"

            scripts.append(
                SegmentScript(
                    segment_index=i,
                    route=route,
                    carrier=seg.carrier,
                    booking_class=booking_class,
                    phone_instruction=instruction,
                    warnings=warnings,
                )
            )

        return scripts

    def _closing_checklist(self, itinerary: Itinerary) -> str:
        """Generate the closing checklist after all segments are booked."""
        t = itinerary.ticket
        plating = t.plating_carrier or "AA"
        pax = t.passengers

        lines = [
            "CLOSING CHECKLIST:",
            "",
            f"  1. Confirm all {len(itinerary.flown_segments)} flown segments are ticketed",
            f"  2. Verify plating carrier is {plating}",
            f"  3. Confirm {pax} passenger(s) on all segments",
            f"  4. Request fare quote — ticket type {t.type.value}",
            "  5. Verify total matches expected fare + YQ surcharges",
            "  6. Ask about change/cancellation flexibility",
        ]

        if t.departure:
            lines.append(
                f"  7. Confirm first segment date lock: {t.departure.strftime('%d %b %Y')}"
            )
            lines.append("     (First segment date is fixed; other dates can change)")

        lines.extend(
            [
                "",
                "  IMPORTANT: Get the PNR/booking reference and save it.",
                "  Ask the agent to email the full itinerary confirmation.",
            ]
        )

        return "\n".join(lines)

    # --- GDS commands (T033) ---

    def _format_gds_date(self, d) -> str:
        """Format a date as GDS date string: 15MAR."""
        if d is None:
            return "01JAN"
        return d.strftime("%d%b").upper()

    def _gds_commands(self, itinerary: Itinerary) -> list[str]:
        """Generate Amadeus GDS commands for the itinerary."""
        t = itinerary.ticket
        origin = t.origin
        cabin = t.cabin
        plating = t.plating_carrier or "AA"
        departure_date = self._format_gds_date(t.departure)

        commands: list[str] = []

        # FQD: fare display (round-trip same city)
        commands.append(f"FQD{origin}{origin}/VRW/D{departure_date}")

        # Segment entries
        for i, seg in enumerate(itinerary.segments):
            if seg.is_surface:
                # Surface shown as ARNK (arrival not known)
                commands.append("ARNK")
                continue

            booking_class = self._get_booking_class(seg.carrier, cabin) or "D"
            date_str = self._format_gds_date(seg.date)
            flight_str = seg.flight or f"{seg.carrier}0000"

            # SS = sell segment: SS[class][count] [flight] [date] [city pair]
            commands.append(
                f"SS {booking_class}1 {flight_str} {date_str} {seg.from_airport}{seg.to_airport}"
            )

        # FXP: pricing
        commands.append("FXP")

        # OSI: other service information
        commands.append("OSI YY OW RTW")

        # Plating carrier override
        commands.append(f"/R,VC-{plating}")

        return commands

    # --- Full generation (T034) ---

    def generate(self, itinerary: Itinerary) -> BookingScript:
        """Generate the complete booking script.

        Combines phone script (opening, per-segment instructions, closing)
        with Amadeus GDS commands and aggregated warnings.
        """
        opening = self._opening_script(itinerary)
        segment_scripts = self._segment_scripts(itinerary)
        closing = self._closing_checklist(itinerary)
        gds = self._gds_commands(itinerary)

        # Collect all warnings from segments plus global warnings
        all_warnings: list[str] = []
        for ss in segment_scripts:
            all_warnings.extend(ss.warnings)

        # Global warning: first segment date lock
        if itinerary.ticket.departure:
            all_warnings.append(
                f"First segment date ({itinerary.ticket.departure.strftime('%d %b %Y')}) "
                f"is locked after ticketing. Other dates remain flexible."
            )

        return BookingScript(
            opening=opening,
            segments=segment_scripts,
            closing=closing,
            gds_commands=gds,
            warnings=all_warnings,
        )
