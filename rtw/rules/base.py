"""Rule engine base: protocol, registry, and decorators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from rtw.models import Itinerary, RuleResult

if TYPE_CHECKING:
    from rtw.validator import ValidationContext


class Rule(Protocol):
    """Protocol for validation rules."""

    rule_id: str
    rule_name: str
    rule_reference: str

    def check(self, itinerary: Itinerary, context: "ValidationContext") -> list[RuleResult]: ...


# Global rule registry
_RULE_REGISTRY: list[type] = []


def register_rule(cls: type) -> type:
    """Decorator to register a rule class."""
    _RULE_REGISTRY.append(cls)
    return cls


def get_registered_rules() -> list[type]:
    """Return all registered rule classes."""
    return list(_RULE_REGISTRY)
