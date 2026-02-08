"""Carrier eligibility rules. Rule 3015 §15, §19."""

from pathlib import Path
import yaml

from rtw.rules.base import register_rule
from rtw.models import RuleResult, Severity

_DATA_DIR = Path(__file__).parent.parent / "data"
with open(_DATA_DIR / "carriers.yaml") as f:
    _CARRIERS = yaml.safe_load(f)

_ELIGIBLE_CODES = {code for code, info in _CARRIERS.items() if info.get("eligible", False)}


@register_rule
class QRNotFirstRule:
    """Qatar Airways cannot be the first carrier."""

    rule_id = "qr_not_first"
    rule_name = "QR Not First Carrier"
    rule_reference = "Rule 3015 §19"

    def check(self, itinerary, context) -> list[RuleResult]:
        # Find first flown segment
        for seg in itinerary.segments:
            if seg.is_flown and seg.carrier:
                if seg.carrier == "QR":
                    return [
                        RuleResult(
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            rule_reference=self.rule_reference,
                            passed=False,
                            severity=Severity.VIOLATION,
                            message="Qatar Airways (QR) cannot be the first carrier on a oneworld Explorer ticket.",
                            fix_suggestion="Start with a different carrier (e.g., RJ for CAI-AMM, CX, BA).",
                        )
                    ]
                else:
                    return [
                        RuleResult(
                            rule_id=self.rule_id,
                            rule_name=self.rule_name,
                            rule_reference=self.rule_reference,
                            passed=True,
                            message=f"First carrier is {seg.carrier} (not QR).",
                        )
                    ]
        return [
            RuleResult(
                rule_id=self.rule_id,
                rule_name=self.rule_name,
                rule_reference=self.rule_reference,
                passed=True,
                message="No flown segments found.",
            )
        ]


@register_rule
class EligibleCarrierRule:
    """All carriers must be oneworld members."""

    rule_id = "eligible_carriers"
    rule_name = "Eligible Carriers"
    rule_reference = "Rule 3015 §15"

    def check(self, itinerary, context) -> list[RuleResult]:
        results = []
        invalid = []
        for i, seg in enumerate(itinerary.segments):
            if seg.is_surface or not seg.carrier:
                continue
            if seg.carrier not in _ELIGIBLE_CODES:
                invalid.append((i, seg.carrier))

        if invalid:
            for idx, carrier in invalid:
                carrier_info = _CARRIERS.get(carrier, {})
                note = carrier_info.get("notes", "")
                results.append(
                    RuleResult(
                        rule_id=self.rule_id,
                        rule_name=self.rule_name,
                        rule_reference=self.rule_reference,
                        passed=False,
                        severity=Severity.VIOLATION,
                        message=f"Segment {idx + 1}: {carrier} is not an eligible oneworld carrier. {note}",
                        fix_suggestion=f"Replace {carrier} with a oneworld member airline.",
                        segments_involved=[idx],
                    )
                )
        else:
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.rule_name,
                    rule_reference=self.rule_reference,
                    passed=True,
                    message="All carriers are eligible oneworld members.",
                )
            )
        return results
