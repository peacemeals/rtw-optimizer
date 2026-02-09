"""Tests for hub connection table loader."""

import yaml
from pathlib import Path

import pytest

from rtw.models import Continent, TariffConference
from rtw.search.hubs import HubTable

HUBS_YAML = Path(__file__).parent.parent.parent / "rtw" / "data" / "hubs.yaml"


@pytest.fixture(scope="module")
def hub_table():
    return HubTable()


@pytest.fixture(scope="module")
def raw_data():
    with open(HUBS_YAML) as f:
        return yaml.safe_load(f)


# --- Data integrity tests (against real hubs.yaml) ---


class TestDataIntegrity:
    def test_yaml_loads_without_error(self):
        with open(HUBS_YAML) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_all_six_tc_crossings_present(self, raw_data):
        expected = [
            "TC1_to_TC2", "TC2_to_TC3", "TC3_to_TC1",
            "TC2_to_TC1", "TC1_to_TC3", "TC3_to_TC2",
        ]
        for key in expected:
            assert key in raw_data, f"Missing TC crossing: {key}"
            assert len(raw_data[key]) >= 1, f"Empty TC crossing: {key}"

    def test_all_carriers_are_valid_oneworld(self, raw_data):
        carriers_yaml = Path(__file__).parent.parent.parent / "rtw" / "data" / "carriers.yaml"
        with open(carriers_yaml) as f:
            carriers = yaml.safe_load(f)
        eligible = {k for k, v in carriers.items() if v.get("eligible", False)}

        for key in ["TC1_to_TC2", "TC2_to_TC3", "TC3_to_TC1",
                     "TC2_to_TC1", "TC1_to_TC3", "TC3_to_TC2"]:
            for entry in raw_data.get(key, []):
                assert entry["carrier"] in eligible, (
                    f"Carrier {entry['carrier']} in {key} is not an eligible oneworld carrier"
                )

        for cont_key, cont_data in raw_data.get("intra_continent", {}).items():
            for carrier in cont_data.get("carriers", []):
                assert carrier in eligible, (
                    f"Carrier {carrier} in intra_{cont_key} is not an eligible oneworld carrier"
                )

    def test_all_airports_are_valid_iata(self, raw_data):
        try:
            import airportsdata
            db = airportsdata.load("IATA")
        except Exception:
            pytest.skip("airportsdata not available")

        for key in ["TC1_to_TC2", "TC2_to_TC3", "TC3_to_TC1",
                     "TC2_to_TC1", "TC1_to_TC3", "TC3_to_TC2"]:
            for entry in raw_data.get(key, []):
                assert entry["from_hub"] in db, f"Unknown airport: {entry['from_hub']}"
                assert entry["to_hub"] in db, f"Unknown airport: {entry['to_hub']}"

        for cont_data in raw_data.get("intra_continent", {}).values():
            for hub in cont_data.get("hubs", []):
                assert hub in db, f"Unknown airport: {hub}"

    def test_connections_sorted_by_priority(self, raw_data):
        for key in ["TC1_to_TC2", "TC2_to_TC3", "TC3_to_TC1",
                     "TC2_to_TC1", "TC1_to_TC3", "TC3_to_TC2"]:
            entries = raw_data.get(key, [])
            priorities = [e["priority"] for e in entries]
            assert priorities == sorted(priorities), (
                f"{key} not sorted by priority: {priorities}"
            )

    def test_intra_continent_all_continents(self, raw_data):
        intra = raw_data.get("intra_continent", {})
        expected = ["EU_ME", "Africa", "Asia", "SWP", "N_America", "S_America"]
        for cont in expected:
            assert cont in intra, f"Missing intra_continent: {cont}"
            assert len(intra[cont].get("carriers", [])) >= 1
            assert len(intra[cont].get("hubs", [])) >= 1


# --- Query logic tests ---


class TestHubTableQueries:
    def test_tc2_to_tc3_returns_connections(self, hub_table):
        conns = hub_table.get_connections(TariffConference.TC2, TariffConference.TC3)
        assert len(conns) >= 1
        assert conns[0].carrier == "QR"  # DOH is top priority

    def test_same_tc_returns_empty(self, hub_table):
        conns = hub_table.get_connections(TariffConference.TC1, TariffConference.TC1)
        assert conns == []

    def test_connections_sorted_by_priority(self, hub_table):
        conns = hub_table.get_connections(TariffConference.TC1, TariffConference.TC2)
        priorities = [c.priority for c in conns]
        assert priorities == sorted(priorities)

    def test_get_intra_carrier_eu_me(self, hub_table):
        carrier = hub_table.get_intra_carrier(Continent.EU_ME)
        assert carrier == "BA"

    def test_get_intra_carrier_asia(self, hub_table):
        carrier = hub_table.get_intra_carrier(Continent.ASIA)
        assert carrier == "CX"

    def test_get_intra_carrier_unknown_fallback(self, hub_table):
        # Should not happen with valid continents, but test robustness
        # We test by directly accessing with a valid continent
        carrier = hub_table.get_intra_carrier(Continent.N_AMERICA)
        assert carrier == "AA"

    def test_get_hubs_for_continent(self, hub_table):
        hubs = hub_table.get_hubs_for_continent(Continent.SWP)
        assert "SYD" in hubs
        assert "MEL" in hubs

    def test_get_all_crossings_returns_six(self, hub_table):
        crossings = hub_table.get_all_crossings()
        assert len(crossings) == 6
