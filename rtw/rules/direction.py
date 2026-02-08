"""Direction of travel and ocean crossing rules. [C§2.6] [C§2.7] Rule 3015 §5."""

from rtw.rules.base import register_rule
from rtw.models import RuleResult, Severity, TariffConference, CONTINENT_TO_TC
from rtw.continents import get_continent


@register_rule
class DirectionOfTravelRule:
    """Travel must be in continuous forward direction between TCs."""

    rule_id = "direction_of_travel"
    rule_name = "Direction of Travel"
    rule_reference = "Rule 3015 §5"

    def check(self, itinerary, context) -> list[RuleResult]:
        tc_seq = context.tc_sequence
        if len(tc_seq) < 2:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message="Insufficient TC transitions to validate direction.",
                )
            ]

        # Determine direction from first TC transition
        tc_order = [TariffConference.TC1, TariffConference.TC2, TariffConference.TC3]

        # Check if the sequence follows a consistent circular direction
        # Eastbound: TC2->TC3->TC1->TC2 or Westbound: TC2->TC1->TC3->TC2
        # Remove consecutive duplicates
        unique_tcs = [tc_seq[0]]
        for tc in tc_seq[1:]:
            if tc != unique_tcs[-1]:
                unique_tcs.append(tc)

        if len(unique_tcs) < 2:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message="Single TC zone — direction not applicable.",
                )
            ]

        # Determine direction from first two distinct TCs
        first, second = unique_tcs[0], unique_tcs[1]
        idx_first = tc_order.index(first)
        idx_second = tc_order.index(second)

        # Eastbound: index increases (with wraparound)
        # TC2(1)->TC3(2) = eastbound, TC3(2)->TC1(0) = eastbound (wrap), TC1(0)->TC2(1) = eastbound
        eastbound = (idx_second - idx_first) % 3 == 1
        direction = "eastbound" if eastbound else "westbound"

        # Verify all transitions follow the same direction
        for i in range(len(unique_tcs) - 1):
            curr = unique_tcs[i]
            next_tc = unique_tcs[i + 1]
            idx_curr = tc_order.index(curr)
            idx_next = tc_order.index(next_tc)
            step = (idx_next - idx_curr) % 3

            if eastbound and step != 1:
                return [
                    RuleResult(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        rule_reference=self.rule_reference,
                        passed=False,
                        severity=Severity.VIOLATION,
                        message=f"Direction reversal detected: {curr.value}->{next_tc.value} breaks {direction} sequence.",
                        fix_suggestion="Reorder segments to maintain continuous forward direction.",
                    )
                ]
            if not eastbound and step != 2:  # Westbound = step of 2 (or -1 mod 3)
                return [
                    RuleResult(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        rule_reference=self.rule_reference,
                        passed=False,
                        severity=Severity.VIOLATION,
                        message=f"Direction reversal detected: {curr.value}->{next_tc.value} breaks {direction} sequence.",
                        fix_suggestion="Reorder segments to maintain continuous forward direction.",
                    )
                ]

        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                rule_reference=self.rule_reference,
                passed=True,
                message=f"Continuous {direction} direction: {' → '.join(tc.value for tc in unique_tcs)}.",
            )
        ]


@register_rule
class OceanCrossingRule:
    """Must cross both Atlantic and Pacific oceans, each once, both flown."""

    rule_id = "ocean_crossings"
    rule_name = "Ocean Crossings"
    rule_reference = "Rule 3015 §5"

    def check(self, itinerary, context) -> list[RuleResult]:
        pacific_crossings = 0
        atlantic_crossings = 0

        for seg in itinerary.segments:
            if seg.is_surface:
                continue

            from_cont = get_continent(seg.from_airport)
            to_cont = get_continent(seg.to_airport)
            if not from_cont or not to_cont:
                continue

            from_tc = CONTINENT_TO_TC[from_cont]
            to_tc = CONTINENT_TO_TC[to_cont]

            # Pacific: TC3 <-> TC1
            if (from_tc == TariffConference.TC3 and to_tc == TariffConference.TC1) or (
                from_tc == TariffConference.TC1 and to_tc == TariffConference.TC3
            ):
                pacific_crossings += 1

            # Atlantic: TC1 <-> TC2
            if (from_tc == TariffConference.TC1 and to_tc == TariffConference.TC2) or (
                from_tc == TariffConference.TC2 and to_tc == TariffConference.TC1
            ):
                atlantic_crossings += 1

        results = []

        if pacific_crossings == 0:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message="No Pacific ocean crossing (TC3↔TC1) found.",
                    fix_suggestion="Add a flown segment between Asia/SWP and the Americas.",
                )
            )
        elif pacific_crossings > 1:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"{pacific_crossings} Pacific crossings — only 1 permitted.",
                    fix_suggestion="Remove extra Pacific crossing segments.",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message="Pacific crossing: 1 (OK).",
                )
            )

        if atlantic_crossings == 0:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message="No Atlantic ocean crossing (TC1↔TC2) found.",
                    fix_suggestion="Add a flown segment between the Americas and Europe/Africa.",
                )
            )
        elif atlantic_crossings > 1:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"{atlantic_crossings} Atlantic crossings — only 1 permitted.",
                    fix_suggestion="Remove extra Atlantic crossing segments.",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message="Atlantic crossing: 1 (OK).",
                )
            )

        return results
