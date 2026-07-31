"""Luma venue extraction — a city is never a venue (the '@ Berlin' bug)."""

from scrapers.luma import pick_venue_name


def test_place_name_wins():
    geo = {"place_name": "FabLab Neukölln", "city": "Berlin"}
    assert pick_venue_name(geo, "FabLab Neukölln, Harzer Str. 39, Berlin", None) == "FabLab Neukölln"


def test_city_is_never_a_venue():
    geo = {"city": "Berlin"}
    assert pick_venue_name(geo, None, None) == "TBA"
    assert pick_venue_name(geo, "Berlin, Deutschland", None) == "TBA"


def test_address_first_segment_beats_city():
    geo = {"city": "Berlin"}
    addr = "The Delta Campus, Donaustraße 44, 12043 Berlin, Deutschland"
    assert pick_venue_name(geo, addr, None) == "The Delta Campus"


def test_name_equal_to_city_is_rejected():
    geo = {"name": "Berlin", "city": "Berlin"}
    assert pick_venue_name(geo, "CIC Berlin, Lohmühlenstraße 65, Berlin", None) == "CIC Berlin"


def test_other_cityish_names_rejected():
    assert pick_venue_name({"city": "Potsdam"}, "Potsdam, Deutschland", None) == "TBA"
