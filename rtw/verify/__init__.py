"""D-class fare verification for oneworld Explorer RTW tickets.

Uses ExpertFlyer to verify booking class availability on candidate
itinerary segments. Business class RTW tickets require D-class on
every flown segment.
"""

from rtw.verify.models import (
    AlternateDateResult,
    DClassResult,
    DClassStatus,
    SegmentVerification,
    VerifyOption,
    VerifyResult,
)

__all__ = [
    "AlternateDateResult",
    "DClassResult",
    "DClassStatus",
    "SegmentVerification",
    "VerifyOption",
    "VerifyResult",
]
