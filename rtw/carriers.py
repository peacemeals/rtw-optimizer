"""Shared carrier booking class resolution.

Resolves the correct booking class for a carrier/cabin combination
using data from carriers.yaml. AA uses H class for oneworld Explorer
business; all other carriers use D.
"""

from pathlib import Path
from typing import Optional

import yaml

from rtw.models import CabinClass

_DATA_DIR = Path(__file__).parent / "data"
with open(_DATA_DIR / "carriers.yaml") as f:
    _CARRIERS: dict = yaml.safe_load(f)


def get_booking_class(carrier: Optional[str], cabin: CabinClass) -> str:
    """Return the booking class for a carrier/cabin combination.

    Business: AA -> H (from carriers.yaml rtw_booking_class), others -> D.
    Economy: L for all carriers.
    First: A for all carriers.
    Surface segments (carrier=None): returns D as safe default.

    Always returns a concrete single-letter string, never None.
    """
    if carrier is None:
        return "D"

    carrier = carrier.upper()

    if cabin == CabinClass.BUSINESS:
        carrier_data = _CARRIERS.get(carrier, {})
        return carrier_data.get("rtw_booking_class", "D")

    if cabin == CabinClass.ECONOMY:
        return "L"

    if cabin == CabinClass.FIRST:
        return "A"

    return "D"
