"""Plain text output formatter -- no ANSI escapes."""

from __future__ import annotations

from rtw.booking import BookingScript
from rtw.models import (
    CostEstimate,
    NTPEstimate,
    SegmentValue,
    ValidationReport,
)


def _header(title: str) -> str:
    """Create a plain text section header."""
    return f"\n{'=' * 60}\n  {title}\n{'=' * 60}\n"


def _subheader(title: str) -> str:
    """Create a plain text sub-header."""
    return f"\n--- {title} ---\n"


class PlainFormatter:
    """Format RTW results as plain text without ANSI escapes."""

    def format_validation(self, report: ValidationReport) -> str:
        """Format a validation report."""
        lines: list[str] = []

        ticket = report.itinerary.ticket
        total = len(report.results)
        passed = sum(1 for r in report.results if r.passed)
        status = "PASS" if report.passed else "FAIL"

        lines.append(_header("Validation Summary"))
        lines.append(f"  Status:     {status}")
        lines.append(
            f"  Ticket:     {ticket.type.value} ({ticket.cabin.value.title()}) from {ticket.origin}"
        )
        lines.append(f"  Passengers: {ticket.passengers}")
        lines.append(
            f"  Segments:   {len(report.itinerary.flown_segments)} flown, "
            f"{len(report.itinerary.surface_segments)} surface"
        )
        lines.append(f"  Rules:      {passed}/{total} passed")
        lines.append(f"  Violations: {report.violation_count}")
        lines.append(f"  Warnings:   {report.warning_count}")

        lines.append(_subheader("Rule Results"))

        # Column headers
        lines.append(f"  {'Rule':<25} {'Status':<8} {'Severity':<12} Message")
        lines.append(f"  {'-' * 25} {'-' * 8} {'-' * 12} {'-' * 40}")

        for r in report.results:
            status_str = "PASS" if r.passed else "FAIL"
            lines.append(f"  {r.rule_name:<25} {status_str:<8} {r.severity.value:<12} {r.message}")
            if not r.passed and r.fix_suggestion:
                lines.append(f"  {'':>25} {'':>8} {'':>12} Fix: {r.fix_suggestion}")

        return "\n".join(lines)

    def format_ntp(self, estimates: list[NTPEstimate]) -> str:
        """Format NTP estimates as a plain text table."""
        lines: list[str] = []
        lines.append(_header("NTP Estimates"))

        # Column headers
        lines.append(
            f"  {'#':>3}  {'Route':<10} {'Carrier':<8} {'Distance':>10} "
            f"{'Method':<9} {'Rate':>6} {'NTP':>10} {'Confidence':<12} Notes"
        )
        lines.append(
            f"  {'-' * 3}  {'-' * 10} {'-' * 8} {'-' * 10} "
            f"{'-' * 9} {'-' * 6} {'-' * 10} {'-' * 12} {'-' * 20}"
        )

        total_ntp = 0.0
        total_distance = 0.0

        for e in estimates:
            rate_str = f"{e.rate:.0%}" if e.rate is not None else "-"
            lines.append(
                f"  {e.segment_index + 1:>3}  {e.route:<10} {e.carrier:<8} "
                f"{e.distance_miles:>10,.0f} {e.method.value:<9} {rate_str:>6} "
                f"{e.estimated_ntp:>10,.0f} {e.confidence:<12} {e.notes}"
            )
            total_ntp += e.estimated_ntp
            total_distance += e.distance_miles

        lines.append(
            f"  {'-' * 3}  {'-' * 10} {'-' * 8} {'-' * 10} "
            f"{'-' * 9} {'-' * 6} {'-' * 10} {'-' * 12} {'-' * 20}"
        )
        lines.append(
            f"  {'':>3}  {'TOTAL':<10} {'':8} {total_distance:>10,.0f} "
            f"{'':9} {'':>6} {total_ntp:>10,.0f}"
        )

        return "\n".join(lines)

    def format_cost(self, estimate: CostEstimate) -> str:
        """Format a cost estimate as plain text."""
        lines: list[str] = []
        lines.append(_header("Cost Estimate"))
        lines.append(f"  Origin:          {estimate.origin}")
        lines.append(f"  Ticket Type:     {estimate.ticket_type.value}")
        lines.append(f"  Base Fare:       ${estimate.base_fare_usd:,.2f}")
        lines.append(f"  Total YQ:        ${estimate.total_yq_usd:,.2f}")
        lines.append(f"  Per Person:      ${estimate.total_per_person_usd:,.2f}")
        lines.append(f"  Passengers:      {estimate.passengers}")
        lines.append(f"  Total All Pax:   ${estimate.total_all_pax_usd:,.2f}")
        lines.append(f"  Plating Carrier: {estimate.plating_carrier}")
        if estimate.notes:
            lines.append(f"  Notes:           {estimate.notes}")
        return "\n".join(lines)

    def format_value(self, values: list[SegmentValue]) -> str:
        """Format segment value analysis as plain text."""
        lines: list[str] = []
        lines.append(_header("Segment Value Analysis"))

        lines.append(
            f"  {'#':>3}  {'Route':<10} {'Carrier':<8} {'J Cost':>10} "
            f"{'Verdict':<12} {'Suggestion':<30} Source"
        )
        lines.append(
            f"  {'-' * 3}  {'-' * 10} {'-' * 8} {'-' * 10} {'-' * 12} {'-' * 30} {'-' * 10}"
        )

        for v in values:
            lines.append(
                f"  {v.segment_index + 1:>3}  {v.route:<10} {v.carrier:<8} "
                f"${v.estimated_j_cost_usd:>9,.0f} {v.verdict:<12} "
                f"{v.suggestion:<30} {v.source}"
            )

        return "\n".join(lines)

    def format_booking(self, script: BookingScript) -> str:
        """Format a booking script as plain text."""
        lines: list[str] = []

        lines.append(_header("Booking Script"))

        # Opening
        lines.append(_subheader("Opening"))
        lines.append(script.opening)

        # Segments
        for seg in script.segments:
            lines.append(_subheader(f"Segment {seg.segment_index + 1}: {seg.route}"))
            lines.append(seg.phone_instruction)
            if seg.warnings:
                for w in seg.warnings:
                    lines.append(f"  WARNING: {w}")

        # Closing
        lines.append(_subheader("Closing Checklist"))
        lines.append(script.closing)

        # GDS
        lines.append(_subheader("GDS Commands (Amadeus)"))
        for cmd in script.gds_commands:
            lines.append(f"  {cmd}")

        # Warnings
        if script.warnings:
            lines.append(_subheader(f"Warnings ({len(script.warnings)})"))
            for w in script.warnings:
                lines.append(f"  - {w}")

        return "\n".join(lines)
