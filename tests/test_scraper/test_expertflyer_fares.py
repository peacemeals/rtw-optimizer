"""Tests for ExpertFlyer fare information scraper."""

import datetime
from unittest.mock import MagicMock

import pytest

from rtw.scraper.expertflyer_fares import (
    DEFAULT_RTW_CARRIERS,
    ExpertFlyerFareScraper,
    FareComparisonResult,
    FareInfo,
    OriginFareResult,
)


class TestFareInfo:
    """Test FareInfo model properties."""

    def test_fare_family_done(self):
        fare = FareInfo(
            fare_basis="DONE4", airline="AA", booking_class="D",
            fare_usd=5957.88,
        )
        assert fare.fare_family == "DONE"

    def test_fare_family_aone(self):
        fare = FareInfo(
            fare_basis="AONE3", airline="AA", booking_class="A",
            fare_usd=9447.05,
        )
        assert fare.fare_family == "AONE"

    def test_fare_family_lone(self):
        fare = FareInfo(
            fare_basis="LONE5", airline="AA", booking_class="L",
            fare_usd=2436.13,
        )
        assert fare.fare_family == "LONE"

    def test_fare_family_glob(self):
        fare = FareInfo(
            fare_basis="DGLOB4", airline="AA", booking_class="D",
            fare_usd=7000.00,
        )
        assert fare.fare_family == "DGLOB"

    def test_continent_count(self):
        fare = FareInfo(
            fare_basis="DONE4", airline="AA", booking_class="D",
            fare_usd=5957.88,
        )
        assert fare.continent_count == 4

    def test_continent_count_6(self):
        fare = FareInfo(
            fare_basis="AONE6", airline="AA", booking_class="A",
            fare_usd=13978.14,
        )
        assert fare.continent_count == 6

    def test_is_rtw_true(self):
        for basis in ["DONE3", "DONE4", "DONE5", "DONE6",
                       "AONE3", "AONE4", "AONE5", "AONE6",
                       "LONE3", "LONE4", "LONE5", "LONE6"]:
            fare = FareInfo(fare_basis=basis, airline="AA",
                          booking_class="D", fare_usd=1000)
            assert fare.is_rtw, f"{basis} should be RTW"

    def test_is_rtw_glob(self):
        for basis in ["DGLOB3", "AGLOB4", "LGLOB5"]:
            fare = FareInfo(fare_basis=basis, airline="AA",
                          booking_class="D", fare_usd=1000)
            assert fare.is_rtw, f"{basis} should be RTW"

    def test_is_rtw_false(self):
        fare = FareInfo(
            fare_basis="YOWRT", airline="AA", booking_class="Y",
            fare_usd=500,
        )
        assert not fare.is_rtw

    def test_model_serialization(self):
        fare = FareInfo(
            fare_basis="DONE4", airline="AA", booking_class="D",
            trip_type="RT", fare_usd=5957.88, cabin="B",
        )
        data = fare.model_dump(mode="json")
        assert data["fare_basis"] == "DONE4"
        assert data["fare_usd"] == pytest.approx(5957.88)
        restored = FareInfo.model_validate(data)
        assert restored.fare_basis == "DONE4"


class TestOriginFareResult:
    """Test OriginFareResult model."""

    @pytest.fixture()
    def osl_result(self):
        return OriginFareResult(
            origin="OSL",
            carriers_queried=["AA", "QR"],
            fares=[
                FareInfo(fare_basis="LONE3", airline="AA", booking_class="L", fare_usd=1772.49),
                FareInfo(fare_basis="LONE4", airline="AA", booking_class="L", fare_usd=2100.10),
                FareInfo(fare_basis="DONE3", airline="AA", booking_class="D", fare_usd=5386.24),
                FareInfo(fare_basis="DONE4", airline="AA", booking_class="D", fare_usd=5957.88),
                FareInfo(fare_basis="DONE4", airline="QR", booking_class="D", fare_usd=6200.00),
                FareInfo(fare_basis="AONE3", airline="AA", booking_class="A", fare_usd=9447.05),
                FareInfo(fare_basis="AONE4", airline="AA", booking_class="A", fare_usd=10901.08),
            ],
        )

    def test_rtw_fares(self, osl_result):
        assert len(osl_result.rtw_fares) == 7

    def test_done_fares(self, osl_result):
        done = osl_result.done_fares
        assert len(done) == 3  # DONE3 AA, DONE4 AA, DONE4 QR
        assert done[0].fare_basis == "DONE3"

    def test_get_fare_returns_cheapest(self, osl_result):
        """get_fare should return cheapest across carriers."""
        fare = osl_result.get_fare("DONE4")
        assert fare is not None
        assert fare.fare_usd == pytest.approx(5957.88)
        assert fare.airline == "AA"

    def test_get_fare_by_carrier(self, osl_result):
        fare = osl_result.get_fare_by_carrier("DONE4", "QR")
        assert fare is not None
        assert fare.fare_usd == pytest.approx(6200.00)

    def test_get_fare_missing(self, osl_result):
        assert osl_result.get_fare("DONE6") is None

    def test_model_serialization(self, osl_result):
        data = osl_result.model_dump(mode="json")
        assert data["origin"] == "OSL"
        assert len(data["fares"]) == 7
        assert data["carriers_queried"] == ["AA", "QR"]
        restored = OriginFareResult.model_validate(data)
        assert restored.origin == "OSL"


class TestFareComparisonResult:
    """Test FareComparisonResult model."""

    @pytest.fixture()
    def comparison(self):
        return FareComparisonResult(
            carriers=["AA", "QR"],
            currency="USD",
            origins=[
                OriginFareResult(
                    origin="OSL", carriers_queried=["AA", "QR"],
                    fares=[
                        FareInfo(fare_basis="DONE4", airline="AA",
                                booking_class="D", fare_usd=5957.88),
                    ],
                ),
                OriginFareResult(
                    origin="NRT", carriers_queried=["AA", "QR"],
                    fares=[
                        FareInfo(fare_basis="DONE4", airline="AA",
                                booking_class="D", fare_usd=5200.00),
                    ],
                ),
                OriginFareResult(
                    origin="BOM", carriers_queried=["AA", "QR"],
                    fares=[
                        FareInfo(fare_basis="DONE4", airline="AA",
                                booking_class="D", fare_usd=4800.00),
                    ],
                ),
            ],
        )

    def test_cheapest_for(self, comparison):
        cheapest = comparison.cheapest_for("DONE4")
        assert cheapest is not None
        assert cheapest.origin == "BOM"

    def test_ranking_for(self, comparison):
        ranking = comparison.ranking_for("DONE4")
        assert len(ranking) == 3
        assert ranking[0] == ("BOM", pytest.approx(4800.00), "AA")
        assert ranking[1] == ("NRT", pytest.approx(5200.00), "AA")
        assert ranking[2] == ("OSL", pytest.approx(5957.88), "AA")

    def test_cheapest_for_missing(self, comparison):
        assert comparison.cheapest_for("AONE6") is None


class TestExpertFlyerFareScraper:
    """Test ExpertFlyerFareScraper URL construction."""

    def test_build_fare_url(self):
        mock_scraper = MagicMock()
        fare_scraper = ExpertFlyerFareScraper(mock_scraper)
        url = fare_scraper._build_fare_url(
            origin="OSL",
            carrier="AA",
            currency="USD",
            date=datetime.date(2026, 2, 9),
        )
        assert "origin=OSL" in url
        assert "destination=OSL" in url
        assert "airLineCodes=AA" in url
        assert "currency=USD" in url
        assert "startDate=2026-02-09" in url
        assert "/air/fare-information/results" in url

    def test_build_fare_url_different_origin(self):
        mock_scraper = MagicMock()
        fare_scraper = ExpertFlyerFareScraper(mock_scraper)
        url = fare_scraper._build_fare_url("NRT", "QR")
        assert "origin=NRT" in url
        assert "destination=NRT" in url
        assert "airLineCodes=QR" in url

    def test_parse_fare_amount(self):
        assert ExpertFlyerFareScraper._parse_fare_amount("$5,957.88") == pytest.approx(5957.88)
        assert ExpertFlyerFareScraper._parse_fare_amount("1772.49") == pytest.approx(1772.49)
        assert ExpertFlyerFareScraper._parse_fare_amount("$12,345") == pytest.approx(12345.0)
        assert ExpertFlyerFareScraper._parse_fare_amount("") == pytest.approx(0.0)
        assert ExpertFlyerFareScraper._parse_fare_amount("N/A") == pytest.approx(0.0)

    def test_default_carriers(self):
        assert "AA" in DEFAULT_RTW_CARRIERS
        assert "QR" in DEFAULT_RTW_CARRIERS
        assert "BA" in DEFAULT_RTW_CARRIERS
        assert "FJ" in DEFAULT_RTW_CARRIERS
        assert "AS" in DEFAULT_RTW_CARRIERS
        assert "RJ" in DEFAULT_RTW_CARRIERS
        assert len(DEFAULT_RTW_CARRIERS) == 6
