"""Stopover rules. Rule 3015 §6."""

from rtw.rules.base import register_rule
from rtw.models import RuleResult, Severity


@register_rule
class MinimumStopoverRule:
    """Minimum 2 stopovers required."""

    rule_id = "minimum_stopovers"
    rule_name = "Minimum Stopovers"
    rule_reference = "Rule 3015 §6"

    def check(self, itinerary, context) -> list[RuleResult]:
        stopovers = [s for s in itinerary.segments if s.is_stopover]
        count = len(stopovers)
        if count < 2:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"Only {count} stopovers — minimum is 2.",
                    fix_suggestion="Change at least 2 transit connections to stopovers (>24h).",
                )
            ]
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                rule_reference=self.rule_reference,
                passed=True,
                message=f"{count} stopovers (minimum: 2).",
            )
        ]


@register_rule
class OriginContinentStopoverRule:
    """Maximum 2 stopovers in continent of origin."""

    rule_id = "origin_continent_stopovers"
    rule_name = "Origin Continent Stopover Limit"
    rule_reference = "Rule 3015 §6"

    def check(self, itinerary, context) -> list[RuleResult]:
        origin_cont = context.origin_continent
        if not origin_cont:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    severity=Severity.INFO,
                    message="Cannot determine origin continent.",
                )
            ]

        count = context.stopovers_per_continent.get(origin_cont, 0)

        if count > 2:
            # Check if this is the MAD-type ambiguity (return leg stopovers)
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.WARNING,
                    message=f"{count} stopovers in origin continent {origin_cont.value} (limit: 2). "
                    f"Verify with AA RTW desk whether return-leg stopovers count.",
                    fix_suggestion="Make intermediate return stops into transits (<24h) or confirm exemption with booking desk.",
                )
            ]

        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                rule_reference=self.rule_reference,
                passed=True,
                message=f"{count}/2 stopovers in origin continent {origin_cont.value}.",
            )
        ]
