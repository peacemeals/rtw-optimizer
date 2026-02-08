"""Ticket validity rules. Rule 3015 §12, §16."""

from rtw.rules.base import register_rule
from rtw.models import RuleResult, Severity
from rtw.continents import are_same_city


@register_rule
class ReturnToOriginRule:
    """Ticket must return to origin city (or same-city group)."""

    rule_id = "return_to_origin"
    rule_name = "Return to Origin"
    rule_reference = "Rule 3015 §18"

    def check(self, itinerary, context) -> list[RuleResult]:
        origin = itinerary.ticket.origin
        if not itinerary.segments:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message="No segments found.",
                )
            ]
        last_dest = itinerary.segments[-1].to_airport
        if are_same_city(origin, last_dest):
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message=f"Returns to origin: {last_dest} (same city as {origin}).",
                )
            ]
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                rule_reference=self.rule_reference,
                passed=False,
                severity=Severity.VIOLATION,
                message=f"Last destination {last_dest} does not match origin {origin}.",
                fix_suggestion=f"Add a final segment returning to {origin}.",
            )
        ]


@register_rule
class ContinentCountRule:
    """Number of continents visited must match ticket type."""

    rule_id = "continent_count"
    rule_name = "Continent Count"
    rule_reference = "Rule 3015 §16"

    def check(self, itinerary, context) -> list[RuleResult]:
        expected = itinerary.ticket.num_continents
        actual = len(context.continents_visited)

        if actual != expected:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.WARNING,
                    message=f"Visiting {actual} continents but ticket is for {expected}. "
                    f"Continents: {', '.join(c.value for c in context.continents_visited)}.",
                    fix_suggestion=f"Adjust ticket type to {'DONE' if itinerary.ticket.fare_prefix == 'D' else 'LONE'}{actual} "
                    f"or modify routing to visit exactly {expected} continents.",
                )
            ]

        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                rule_reference=self.rule_reference,
                passed=True,
                message=f"{actual} continents: {', '.join(c.value for c in context.continents_visited)}.",
            )
        ]


@register_rule
class TicketValidityRule:
    """Ticket valid for 10-365 days."""

    rule_id = "ticket_validity"
    rule_name = "Ticket Validity Period"
    rule_reference = "Rule 3015 §12"

    def check(self, itinerary, context) -> list[RuleResult]:
        # Get first and last dates
        dates = [s.date for s in itinerary.segments if s.date is not None]
        if len(dates) < 2:
            return [
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    severity=Severity.INFO,
                    message="Insufficient dates to check validity period.",
                )
            ]

        first_date = min(dates)
        last_date = max(dates)
        days = (last_date - first_date).days

        results = []
        if days < 10:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"Trip duration {days} days — minimum is 10 days.",
                    fix_suggestion="Extend itinerary to at least 10 days.",
                )
            )
        elif days > 365:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=False,
                    severity=Severity.VIOLATION,
                    message=f"Trip duration {days} days — maximum is 365 days (1 year).",
                    fix_suggestion="Shorten itinerary to fit within 12 months.",
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message=f"Trip duration: {days} days (valid: 10-365).",
                )
            )

        return results
