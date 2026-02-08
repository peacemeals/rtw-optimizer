"""Smoke tests to verify basic project setup."""

from pathlib import Path


def test_fixtures_dir_exists():
    assert (Path(__file__).parent / "fixtures").is_dir()


def test_v3_fixture_loads(v3_itinerary):
    assert v3_itinerary is not None
    assert v3_itinerary["ticket"]["type"] == "DONE4"
    assert v3_itinerary["ticket"]["origin"] == "CAI"
    assert len(v3_itinerary["segments"]) == 16


def test_rtw_importable():
    import rtw

    assert rtw is not None
