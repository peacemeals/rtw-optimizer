"""Tests for search query parsing and validation."""

from datetime import date, timedelta

import pytest

from rtw.search.query import parse_search_query


TODAY = date.today()
FUTURE = TODAY + timedelta(days=60)
FUTURE_END = TODAY + timedelta(days=120)


class TestValidQueries:
    def test_valid_3_city_query(self):
        q = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
        )
        assert len(q.cities) == 3
        assert q.origin == "SYD"

    def test_valid_5_city_query(self):
        # 5 continents: EU_ME(LHR), Asia(NRT), N_America(JFK), SWP(SYD), S_America(SCL)
        q = parse_search_query(
            cities=["LHR", "NRT", "JFK", "SYD", "SCL"],
            origin="CAI",
            date_from=FUTURE,
            date_to=FUTURE_END,
            ticket_type="DONE5",
        )
        assert len(q.cities) == 5

    def test_valid_8_city_query(self):
        # 6 continents: EU_ME(LHR,DOH), Asia(NRT,HKG), N_America(JFK,LAX), SWP(SYD), S_America(SCL), Africa(NBO)
        q = parse_search_query(
            cities=["LHR", "NRT", "JFK", "SYD", "HKG", "NBO", "SCL", "LAX"],
            origin="CAI",
            date_from=FUTURE,
            date_to=FUTURE_END,
            ticket_type="DONE6",
        )
        assert len(q.cities) == 8

    def test_lowercase_cities_uppercased(self):
        q = parse_search_query(
            cities=["lhr", "nrt", "jfk"],
            origin="syd",
            date_from=FUTURE,
            date_to=FUTURE_END,
        )
        assert q.cities == ["LHR", "NRT", "JFK"]
        assert q.origin == "SYD"

    def test_cabin_and_ticket_type(self):
        q = parse_search_query(
            cities=["LHR", "NRT", "JFK"],
            origin="SYD",
            date_from=FUTURE,
            date_to=FUTURE_END,
            cabin="first",
            ticket_type="AONE3",
        )
        assert q.cabin.value == "first"
        assert q.ticket_type.value == "AONE3"


class TestCityCountValidation:
    def test_fewer_than_3_cities_rejected(self):
        with pytest.raises(ValueError, match="requires 3-8 airports"):
            parse_search_query(
                cities=["LHR", "NRT"],
                origin="SYD",
                date_from=FUTURE,
                date_to=FUTURE_END,
            )

    def test_more_than_8_cities_rejected(self):
        with pytest.raises(ValueError, match="allows maximum 8"):
            parse_search_query(
                cities=["LHR", "NRT", "JFK", "SYD", "HKG", "DEL", "DOH", "LAX", "MIA"],
                origin="CAI",
                date_from=FUTURE,
                date_to=FUTURE_END,
            )


class TestIATAValidation:
    def test_invalid_iata_code_rejected(self):
        with pytest.raises(ValueError, match="Unknown airport code"):
            parse_search_query(
                cities=["LHR", "NRT", "XYZ"],
                origin="SYD",
                date_from=FUTURE,
                date_to=FUTURE_END,
            )

    def test_invalid_origin_rejected(self):
        with pytest.raises(ValueError, match="Unknown airport code"):
            parse_search_query(
                cities=["LHR", "NRT", "JFK"],
                origin="ZZZ",
                date_from=FUTURE,
                date_to=FUTURE_END,
            )

    def test_duplicate_cities_rejected(self):
        with pytest.raises(ValueError, match="Duplicate city"):
            parse_search_query(
                cities=["LHR", "NRT", "LHR"],
                origin="SYD",
                date_from=FUTURE,
                date_to=FUTURE_END,
            )


class TestDateValidation:
    def test_past_date_rejected(self):
        past = TODAY - timedelta(days=10)
        with pytest.raises(ValueError, match="is in the past"):
            parse_search_query(
                cities=["LHR", "NRT", "JFK"],
                origin="SYD",
                date_from=past,
                date_to=FUTURE_END,
            )

    def test_reversed_dates_rejected(self):
        with pytest.raises(ValueError, match="is after --to date"):
            parse_search_query(
                cities=["LHR", "NRT", "JFK"],
                origin="SYD",
                date_from=FUTURE_END,
                date_to=FUTURE,
            )


class TestCabinTicketValidation:
    def test_invalid_cabin_rejected(self):
        with pytest.raises(ValueError, match="Invalid cabin class"):
            parse_search_query(
                cities=["LHR", "NRT", "JFK"],
                origin="SYD",
                date_from=FUTURE,
                date_to=FUTURE_END,
                cabin="premium_economy",
            )

    def test_invalid_ticket_type_rejected(self):
        with pytest.raises(ValueError, match="Invalid ticket type"):
            parse_search_query(
                cities=["LHR", "NRT", "JFK"],
                origin="SYD",
                date_from=FUTURE,
                date_to=FUTURE_END,
                ticket_type="INVALID",
            )


class TestContinentCoverage:
    def test_insufficient_continents_rejected(self):
        # All 3 cities in same TC (Europe) for DONE4 (needs 4 continents)
        with pytest.raises(ValueError, match="Insufficient continents"):
            parse_search_query(
                cities=["LHR", "MAD", "CDG"],
                origin="CAI",
                date_from=FUTURE,
                date_to=FUTURE_END,
                ticket_type="DONE4",
            )

    def test_origin_counts_toward_continents(self):
        # 3 cities in 2 continents + origin in 3rd = 3 continents for DONE3
        q = parse_search_query(
            cities=["LHR", "NRT", "HKG"],
            origin="JFK",
            date_from=FUTURE,
            date_to=FUTURE_END,
            ticket_type="DONE3",
        )
        assert q is not None
