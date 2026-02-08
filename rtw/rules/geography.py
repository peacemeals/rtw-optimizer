"""Geography-specific rules: Hawaii, Alaska, Australia, Transcontinental. Rule 3015 §9-10."""

from rtw.rules.base import register_rule
from rtw.models import RuleResult, Severity

# Hawaii airports
_HAWAII_AIRPORTS = {"HNL", "OGG", "KOA", "LIH", "ITO"}
# Alaska airports
_ALASKA_AIRPORTS = {"ANC", "FAI", "JNU", "SIT", "KTN"}
# US mainland (approximate — for transcontinental check)
_US_EAST = {
    "JFK",
    "LGA",
    "EWR",
    "BOS",
    "PHL",
    "DCA",
    "IAD",
    "BWI",
    "ATL",
    "MIA",
    "MCO",
    "FLL",
    "TPA",
    "CLT",
    "RDU",
    "PIT",
    "DTW",
    "CLE",
    "CVG",
    "IND",
    "MSP",
    "STL",
    "MCI",
    "MSY",
    "BNA",
    "MEM",
    "ORD",
    "MDW",
}
_US_WEST = {
    "LAX",
    "SFO",
    "SEA",
    "PDX",
    "SAN",
    "SJC",
    "OAK",
    "SMF",
    "LAS",
    "PHX",
    "DEN",
    "SLC",
    "DFW",
    "IAH",
    "AUS",
    "SAT",
}


@register_rule
class HawaiiAlaskaRule:
    """Hawaii backtracking banned. Alaska: only 1 flight to, 1 from."""

    rule_id = "hawaii_alaska"
    rule_name = "Hawaii & Alaska Restrictions"
    rule_reference = "Rule 3015 §5, §10"

    def check(self, itinerary, context) -> list[RuleResult]:
        results = []

        # Hawaii backtracking check
        visited_hawaii = False
        left_hawaii = False
        for seg in itinerary.segments:
            if seg.is_surface:
                continue
            if seg.to_airport in _HAWAII_AIRPORTS:
                if left_hawaii:
                    results.append(
                        RuleResult(
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            rule_reference=self.rule_reference,
                            passed=False,
                            severity=Severity.VIOLATION,
                            message="Backtracking to Hawaii after leaving is not permitted.",
                            fix_suggestion="Remove the return flight to Hawaii or restructure routing.",
                        )
                    )
                visited_hawaii = True
            elif visited_hawaii and seg.from_airport in _HAWAII_AIRPORTS:
                left_hawaii = True

        # Alaska flight count
        to_alaska = sum(
            1 for s in itinerary.segments if s.is_flown and s.to_airport in _ALASKA_AIRPORTS
        )
        from_alaska = sum(
            1 for s in itinerary.segments if s.is_flown and s.from_airport in _ALASKA_AIRPORTS
        )

        if to_alaska > 1:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"{to_alaska} flights TO Alaska — only 1 permitted.",
                    fix_suggestion="Remove extra flights to Alaska.",
                )
            )
        if from_alaska > 1:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"{from_alaska} flights FROM Alaska — only 1 permitted.",
                    fix_suggestion="Remove extra flights from Alaska.",
                )
            )

        if not results:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message="Hawaii/Alaska restrictions: OK.",
                )
            )

        return results


@register_rule
class TranscontinentalUSRule:
    """Only one nonstop transcontinental flight within USA/Canada."""

    rule_id = "transcontinental_us"
    rule_name = "US Transcontinental Limit"
    rule_reference = "Rule 3015 §10"

    def check(self, itinerary, context) -> list[RuleResult]:
        transcon_count = 0
        for seg in itinerary.segments:
            if seg.is_surface:
                continue
            from_east = seg.from_airport in _US_EAST
            from_west = seg.from_airport in _US_WEST
            to_east = seg.to_airport in _US_EAST
            to_west = seg.to_airport in _US_WEST

            if (from_east and to_west) or (from_west and to_east):
                transcon_count += 1

        if transcon_count > 1:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"{transcon_count} transcontinental US flights — only 1 permitted.",
                    fix_suggestion="Route through an intermediate hub to avoid nonstop transcontinental.",
                )
            ]

        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                rule_reference=self.rule_reference,
                passed=True,
                message=f"US transcontinental flights: {transcon_count}/1.",
            )
        ]
