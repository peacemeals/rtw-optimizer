"""Surface sector rules. Rule 3015 §7."""

from rtw.rules.base import register_rule
from rtw.models import RuleResult, Severity


@register_rule
class SameCityResolutionRule:
    """Same-city airport pairs (NRT/HND, TSA/TPE) are NOT surface sectors."""

    rule_id = "same_city_resolution"
    rule_name = "Same-City Resolution"
    rule_reference = "Rule 3015 §7"

    def check(self, itinerary, context) -> list[RuleResult]:
        results = []
        for i, (seg_idx, next_idx) in enumerate(context.same_city_pairs):
            arr = itinerary.segments[seg_idx].to_airport
            dep = itinerary.segments[next_idx].from_airport
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    severity=Severity.INFO,
                    message=f"Same-city pair: {arr}/{dep} (not a surface sector).",
                    segments_involved=[seg_idx, next_idx],
                )
            )
        if not results:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message="No same-city pairs detected.",
                )
            )
        return results
