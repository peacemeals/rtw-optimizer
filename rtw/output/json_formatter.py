"""JSON output formatter -- valid JSON suitable for piping to jq."""

from __future__ import annotations

import json

from rtw.booking import BookingScript
from rtw.models import (
    CostEstimate,
    NTPEstimate,
    SegmentValue,
    ValidationReport,
)


class JsonFormatter:
    """Format RTW results as pretty-printed JSON."""

    def format_validation(self, report: ValidationReport) -> str:
        """Format a validation report as JSON."""
        data = {
            "type": "validation_report",
            "summary": {
                "passed": report.passed,
                "violation_count": report.violation_count,
                "warning_count": report.warning_count,
                "total_rules": len(report.results),
            },
            "ticket": report.itinerary.ticket.model_dump(mode="json"),
            "results": [r.model_dump(mode="json") for r in report.results],
        }
        return json.dumps(data, indent=2)

    def format_ntp(self, estimates: list[NTPEstimate]) -> str:
        """Format NTP estimates as JSON."""
        total_ntp = sum(e.estimated_ntp for e in estimates)
        total_distance = sum(e.distance_miles for e in estimates)
        data = {
            "type": "ntp_estimates",
            "summary": {
                "total_ntp": total_ntp,
                "total_distance_miles": total_distance,
                "segment_count": len(estimates),
            },
            "estimates": [e.model_dump(mode="json") for e in estimates],
        }
        return json.dumps(data, indent=2)

    def format_cost(self, estimate: CostEstimate) -> str:
        """Format a cost estimate as JSON."""
        data = {
            "type": "cost_estimate",
            **estimate.model_dump(mode="json"),
        }
        return json.dumps(data, indent=2)

    def format_value(self, values: list[SegmentValue]) -> str:
        """Format segment value analysis as JSON."""
        data = {
            "type": "segment_value_analysis",
            "segment_count": len(values),
            "values": [v.model_dump(mode="json") for v in values],
        }
        return json.dumps(data, indent=2)

    def format_booking(self, script: BookingScript) -> str:
        """Format a booking script as JSON."""
        data = {
            "type": "booking_script",
            **script.model_dump(mode="json"),
        }
        return json.dumps(data, indent=2)
