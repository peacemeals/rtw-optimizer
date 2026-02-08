"""Output formatters for RTW Optimizer.

Provides a Formatter protocol and three implementations:
- RichFormatter: colored Rich tables and panels
- PlainFormatter: plain text without ANSI escapes
- JsonFormatter: valid JSON for piping to jq
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rtw.booking import BookingScript
    from rtw.models import CostEstimate, NTPEstimate, SegmentValue, ValidationReport


class Formatter(Protocol):
    """Protocol for formatting RTW analysis results."""

    def format_validation(self, report: ValidationReport) -> str:
        """Format a validation report."""
        ...

    def format_ntp(self, estimates: list[NTPEstimate]) -> str:
        """Format NTP estimates."""
        ...

    def format_cost(self, estimate: CostEstimate) -> str:
        """Format a cost estimate."""
        ...

    def format_value(self, values: list[SegmentValue]) -> str:
        """Format segment value analysis."""
        ...

    def format_booking(self, script: BookingScript) -> str:
        """Format a booking script."""
        ...


def get_formatter(name: str = "rich") -> Formatter:
    """Get a formatter by name.

    Args:
        name: One of "rich", "plain", "json".

    Returns:
        A Formatter instance.

    Raises:
        ValueError: If the name is not recognized.
    """
    if name == "rich":
        from rtw.output.rich_formatter import RichFormatter

        return RichFormatter()
    elif name == "plain":
        from rtw.output.plain_formatter import PlainFormatter

        return PlainFormatter()
    elif name == "json":
        from rtw.output.json_formatter import JsonFormatter

        return JsonFormatter()
    else:
        raise ValueError(f"Unknown formatter: {name!r}. Use 'rich', 'plain', or 'json'.")
