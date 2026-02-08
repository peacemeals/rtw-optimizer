"""Intercontinental arrival/departure limit rule. Rule 3015 SS4(e)."""

from rtw.rules.base import register_rule
from rtw.models import Continent, RuleResult, Severity


@register_rule
class IntercontinentalLimitRule:
    """Max 1 intercontinental arrival + 1 departure per continent.

    Exceptions (Rule 3015 Section 4e):
    - North America: always allows 2
    - Asia: allows 2 when bridging SWP and Europe/Middle East
    - Europe/Middle East: allows 2 for travel to/from/via Africa
    """

    rule_id = "intercontinental_limit"
    rule_name = "Intercontinental Arrival/Departure Limit"
    rule_reference = "Rule 3015 SS4(e)"

    DEFAULT_LIMIT = 1
    NA_LIMIT = 2

    def check(self, itinerary, context) -> list[RuleResult]:
        results = []

        all_conts = set(context.intercontinental_arrivals.keys()) | set(
            context.intercontinental_departures.keys()
        )

        for continent in sorted(all_conts, key=lambda c: c.value):
            arrivals = context.intercontinental_arrivals.get(continent, 0)
            departures = context.intercontinental_departures.get(continent, 0)
            limit = self._get_limit(continent, context)

            if arrivals > limit:
                results.append(
                    RuleResult(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        rule_reference=self.rule_reference,
                        passed=False,
                        severity=Severity.VIOLATION,
                        message=(
                            f"{continent.value}: {arrivals} intercontinental "
                            f"arrivals exceeds limit of {limit}."
                        ),
                        fix_suggestion=(
                            f"Reduce intercontinental arrivals in "
                            f"{continent.value} to {limit}."
                        ),
                    )
                )

            if departures > limit:
                results.append(
                    RuleResult(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        rule_reference=self.rule_reference,
                        passed=False,
                        severity=Severity.VIOLATION,
                        message=(
                            f"{continent.value}: {departures} intercontinental "
                            f"departures exceeds limit of {limit}."
                        ),
                        fix_suggestion=(
                            f"Reduce intercontinental departures from "
                            f"{continent.value} to {limit}."
                        ),
                    )
                )

            if arrivals <= limit and departures <= limit:
                results.append(
                    RuleResult(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        rule_reference=self.rule_reference,
                        passed=True,
                        severity=Severity.INFO,
                        message=(
                            f"{continent.value}: {arrivals}/{limit} "
                            f"intercontinental arrivals, "
                            f"{departures}/{limit} departures."
                        ),
                    )
                )

        if not all_conts:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message="No intercontinental segments detected.",
                )
            )

        return results

    def _get_limit(self, continent, context) -> int:
        """Determine the intercontinental limit for a continent."""
        if continent == Continent.N_AMERICA:
            return self.NA_LIMIT

        if continent == Continent.ASIA:
            if self._asia_bridge_applies(context):
                return 2

        if continent == Continent.EU_ME:
            if self._eu_me_africa_applies(context):
                return 2

        return self.DEFAULT_LIMIT

    @staticmethod
    def _asia_bridge_applies(context) -> bool:
        """Asia gets 2 when itinerary bridges SWP and EU_ME through Asia."""
        visited = set(context.continents_visited)
        return Continent.SWP in visited and Continent.EU_ME in visited

    @staticmethod
    def _eu_me_africa_applies(context) -> bool:
        """EU/ME gets 2 when itinerary includes Africa."""
        return Continent.AFRICA in set(context.continents_visited)
