"""Hub connection table loader for RTW route generation."""

from pathlib import Path
from typing import Optional

import yaml

from rtw.models import Continent, TariffConference, CONTINENT_TO_TC

_DATA_DIR = Path(__file__).parent.parent / "data"

# Map continent enum to intra_continent YAML keys
_CONTINENT_KEY = {
    Continent.EU_ME: "EU_ME",
    Continent.AFRICA: "Africa",
    Continent.ASIA: "Asia",
    Continent.SWP: "SWP",
    Continent.N_AMERICA: "N_America",
    Continent.S_AMERICA: "S_America",
}

# Map TC pairs to YAML section keys
_TC_PAIR_KEY = {
    (TariffConference.TC1, TariffConference.TC2): "TC1_to_TC2",
    (TariffConference.TC2, TariffConference.TC3): "TC2_to_TC3",
    (TariffConference.TC3, TariffConference.TC1): "TC3_to_TC1",
    (TariffConference.TC2, TariffConference.TC1): "TC2_to_TC1",
    (TariffConference.TC1, TariffConference.TC3): "TC1_to_TC3",
    (TariffConference.TC3, TariffConference.TC2): "TC3_to_TC2",
}


class HubConnection:
    """A single hub-to-hub connection."""

    __slots__ = ("from_hub", "to_hub", "carrier", "priority")

    def __init__(self, from_hub: str, to_hub: str, carrier: str, priority: int):
        self.from_hub = from_hub
        self.to_hub = to_hub
        self.carrier = carrier
        self.priority = priority

    def __repr__(self) -> str:
        return f"HubConnection({self.from_hub}->{self.to_hub} {self.carrier} p{self.priority})"


class HubTable:
    """Loads and queries the hub connection YAML."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or (_DATA_DIR / "hubs.yaml")
        with open(self._path) as f:
            self._data = yaml.safe_load(f)
        self._connections: dict[str, list[HubConnection]] = {}
        self._intra: dict[str, dict] = self._data.get("intra_continent", {})
        self._load_connections()

    def _load_connections(self) -> None:
        for key in _TC_PAIR_KEY.values():
            entries = self._data.get(key, [])
            conns = [
                HubConnection(
                    from_hub=e["from_hub"],
                    to_hub=e["to_hub"],
                    carrier=e["carrier"],
                    priority=e["priority"],
                )
                for e in entries
            ]
            conns.sort(key=lambda c: c.priority)
            self._connections[key] = conns

    def get_connections(
        self, from_tc: TariffConference, to_tc: TariffConference
    ) -> list[HubConnection]:
        """Get hub connections between two TCs, sorted by priority.

        Returns empty list if from_tc == to_tc (same-TC, no intercontinental needed).
        """
        if from_tc == to_tc:
            return []
        key = _TC_PAIR_KEY.get((from_tc, to_tc))
        if key is None:
            return []
        return list(self._connections.get(key, []))

    def get_intra_carrier(self, continent: Continent) -> str:
        """Get the primary carrier for intra-continent flights.

        Returns first carrier in the list for the continent, or "AA" as fallback.
        """
        key = _CONTINENT_KEY.get(continent)
        if key and key in self._intra:
            carriers = self._intra[key].get("carriers", [])
            if carriers:
                return carriers[0]
        return "AA"

    def get_hubs_for_continent(self, continent: Continent) -> list[str]:
        """Get hub airports for a continent."""
        key = _CONTINENT_KEY.get(continent)
        if key and key in self._intra:
            return list(self._intra[key].get("hubs", []))
        return []

    def get_all_crossings(self) -> list[str]:
        """Return all TC crossing section keys that have connections."""
        return [k for k, v in self._connections.items() if v]
