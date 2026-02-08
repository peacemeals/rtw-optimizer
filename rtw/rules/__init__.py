"""Rule engine package -- auto-discovers all rule modules."""

from rtw.rules.base import get_registered_rules, register_rule, Rule

__all__ = ["get_registered_rules", "register_rule", "Rule"]
