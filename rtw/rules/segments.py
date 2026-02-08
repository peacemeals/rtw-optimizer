"""Segment count and per-continent limit rules. [C§2.5] Rule 3015 §4."""

from rtw.rules.base import register_rule
from rtw.models import RuleResult, Severity
from rtw.continents import get_segment_limit


@register_rule
class SegmentCountRule:
    """Total segments must be 3-16 (including surface sectors)."""

    rule_id = "segment_count"
    rule_name = "Segment Count"
    rule_reference = "Rule 3015 §4"

    def check(self, itinerary, context) -> list[RuleResult]:
        total = len(itinerary.segments)
        if total < 3:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"Only {total} segments — minimum is 3.",
                    fix_suggestion="Add more segments to reach at least 3.",
                )
            ]
        if total > 16:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"{total} segments exceeds maximum of 16 (including surface sectors).",
                    fix_suggestion="Remove segments or convert some to side trips.",
                )
            ]
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                rule_reference=self.rule_reference,
                passed=True,
                message=f"{total} segments (limit: 16).",
            )
        ]


@register_rule
class PerContinentLimitRule:
    """Per-continent intra-continental segment limits: 4 for most, 6 for North America.

    Only intra-continental segments (from_continent == to_continent) count.
    Intercontinental segments are validated by IntercontinentalLimitRule.
    """

    rule_id = "per_continent_limit"
    rule_name = "Per-Continent Segment Limit"
    rule_reference = "Rule 3015 §4"

    def check(self, itinerary, context) -> list[RuleResult]:
        results = []
        for continent, count in context.segments_per_continent.items():
            limit = get_segment_limit(continent)
            if count > limit:
                results.append(
                    RuleResult(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        rule_reference=self.rule_reference,
                        passed=False,
                        severity=Severity.VIOLATION,
                        message=f"{continent.value}: {count} segments exceeds limit of {limit}.",
                        fix_suggestion=f"Reduce segments in {continent.value} to {limit} or fewer.",
                    )
                )
            else:
                results.append(
                    RuleResult(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        rule_reference=self.rule_reference,
                        passed=True,
                        message=f"{continent.value}: {count}/{limit} segments.",
                    )
                )
        return results
