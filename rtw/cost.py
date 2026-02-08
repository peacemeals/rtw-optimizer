"""Cost estimator for RTW itineraries.

Estimates base fares, carrier-imposed surcharges (YQ), plating carrier
comparisons, and total trip cost.

Data loaded from:
- rtw/data/fares.yaml (base fares by origin and ticket type)
- rtw/data/surcharges.yaml (per-carrier YQ and plating comparison)
- rtw/data/carriers.yaml (carrier reference with yq_estimate_per_segment)
"""

from pathlib import Path

import yaml

from rtw.models import CostEstimate, Itinerary, TicketType

_DATA_DIR = Path(__file__).parent / "data"

# Major US airport codes for AA domestic zero-YQ rule
_US_AIRPORTS = {
    "JFK",
    "EWR",
    "LGA",
    "LAX",
    "SFO",
    "ORD",
    "DFW",
    "MIA",
    "ATL",
    "SEA",
    "BOS",
    "DEN",
    "PHX",
    "MCO",
    "IAD",
    "IAH",
    "CLT",
    "PHL",
    "SAN",
    "AUS",
    "MSP",
    "DTW",
    "SLC",
    "HNL",
    "OGG",
    "TPA",
    "FLL",
    "BWI",
    "DCA",
    "STL",
    "PDX",
    "BNA",
    "RDU",
    "CLE",
    "PIT",
    "IND",
    "MCI",
    "OAK",
    "SJC",
    "SMF",
    "ABQ",
    "ANC",
}


class CostEstimator:
    """Estimate costs for oneworld Explorer RTW tickets."""

    def __init__(self) -> None:
        with open(_DATA_DIR / "fares.yaml") as f:
            self._fares = yaml.safe_load(f)

        with open(_DATA_DIR / "surcharges.yaml") as f:
            self._surcharges = yaml.safe_load(f)

        with open(_DATA_DIR / "carriers.yaml") as f:
            self._carriers = yaml.safe_load(f)

    def get_base_fare(self, origin: str, ticket_type: TicketType) -> float:
        """Look up base fare for an origin and ticket type.

        Returns 0.0 if origin or ticket type not found.
        """
        origin = origin.upper()
        origins = self._fares.get("origins", {})
        origin_data = origins.get(origin, {})
        fares = origin_data.get("fares", {})
        return float(fares.get(ticket_type.value, 0.0))

    def compare_origins(self, ticket_type: TicketType) -> list[dict]:
        """Compare all origins for a ticket type, sorted cheapest first.

        Returns list of dicts with keys: origin, name, fare_usd, currency, notes.
        """
        origins = self._fares.get("origins", {})
        results = []
        for code, data in origins.items():
            fare = data.get("fares", {}).get(ticket_type.value, 0)
            if fare > 0:
                results.append(
                    {
                        "origin": code,
                        "name": data.get("name", code),
                        "fare_usd": float(fare),
                        "currency": data.get("currency", "USD"),
                        "notes": data.get("notes", ""),
                    }
                )
        results.sort(key=lambda x: x["fare_usd"])
        return results

    def estimate_surcharges(self, itinerary: Itinerary, plating_carrier: str = "AA") -> float:
        """Estimate total YQ surcharges for an itinerary.

        Rules:
        - Surface segments: $0 YQ
        - AA domestic (US-US): $0 YQ
        - Other segments: use carrier's yq_estimate_per_segment from
          carriers.yaml, falling back to surcharges.yaml carrier_yq
        """
        carrier_yq = self._surcharges.get("carrier_yq", {})
        total = 0.0

        for seg in itinerary.segments:
            # Surface segments: zero YQ
            if seg.is_surface:
                continue

            carrier = seg.carrier or ""

            # AA domestic (both airports in US): zero YQ
            if carrier == "AA" and self._is_us_domestic(seg.from_airport, seg.to_airport):
                continue

            # Look up per-segment YQ: carriers.yaml first, then surcharges.yaml
            carrier_data = self._carriers.get(carrier, {})
            yq = carrier_data.get("yq_estimate_per_segment")
            if yq is None:
                yq = carrier_yq.get(carrier, 0)

            total += float(yq)

        return total

    def compare_plating(self, itinerary: Itinerary) -> list[dict]:
        """Compare plating carrier options for an itinerary.

        Returns list sorted by total estimated cost (base + YQ), cheapest first.
        Each dict: plating_carrier, name, total_yq_usd, flexibility, notes.
        """
        plating = self._surcharges.get("plating_comparison", {})
        results = []

        for code, data in plating.items():
            carrier_data = self._carriers.get(code, {})
            results.append(
                {
                    "plating_carrier": code,
                    "name": carrier_data.get("name", code),
                    "total_yq_usd": float(data.get("typical_total_yq_usd", 0)),
                    "flexibility": data.get("flexibility", "unknown"),
                    "notes": data.get("notes", ""),
                }
            )

        results.sort(key=lambda x: x["total_yq_usd"])
        return results

    def estimate_total(self, itinerary: Itinerary, plating_carrier: str = "AA") -> CostEstimate:
        """Estimate total cost for an itinerary.

        Sums base_fare + total_yq per person, then multiplies by passengers.
        """
        origin = itinerary.ticket.origin
        ticket_type = itinerary.ticket.type
        passengers = itinerary.ticket.passengers

        base_fare = self.get_base_fare(origin, ticket_type)
        total_yq = self.estimate_surcharges(itinerary, plating_carrier)
        per_person = base_fare + total_yq
        total_all = per_person * passengers

        # Build notes
        notes_parts = []
        plating_data = self._surcharges.get("plating_comparison", {}).get(plating_carrier, {})
        if plating_data:
            notes_parts.append(plating_data.get("notes", ""))
        if plating_carrier == "AA":
            notes_parts.append("AA RTW desk offers best flexibility for mid-trip changes.")

        return CostEstimate(
            origin=origin,
            ticket_type=ticket_type,
            base_fare_usd=base_fare,
            total_yq_usd=total_yq,
            total_per_person_usd=per_person,
            total_all_pax_usd=total_all,
            passengers=passengers,
            plating_carrier=plating_carrier,
            notes=" ".join(notes_parts),
        )

    @staticmethod
    def _is_us_domestic(from_airport: str, to_airport: str) -> bool:
        """Check if both airports are in the US."""
        return from_airport in _US_AIRPORTS and to_airport in _US_AIRPORTS
