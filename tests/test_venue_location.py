from pipeline.venue_location import (
    fields_from_reverse_result,
    normalize_neighborhood,
    parse_address,
)


def test_parse_address_with_city() -> None:
    assert parse_address("Landsberger Allee 61, 10249 Berlin") == {
        "postal_code": "10249",
        "city": "Berlin",
    }


def test_parse_address_tolerates_extra_comma() -> None:
    assert parse_address("Heinrich-Dathe-Platz 1, 10319, Berlin") == {
        "postal_code": "10319",
        "city": "Berlin",
    }


def test_parse_address_does_not_invent_missing_postcode() -> None:
    assert parse_address("Markgrafendamm 24c, Berlin") == {}


def test_normalize_neighborhood_rejects_city_placeholder() -> None:
    assert normalize_neighborhood(" Berlin ", city="Berlin") is None
    assert normalize_neighborhood("Prenzlauer Berg", city="Berlin") == "Prenzlauer Berg"


def test_reverse_result_maps_structured_fields() -> None:
    result = {
        "address": {
            "postcode": "10437",
            "city": "Berlin",
            "borough": "Bezirk Pankow",
            "suburb": "Prenzlauer Berg",
            "country_code": "de",
        }
    }
    assert fields_from_reverse_result(result) == {
        "postal_code": "10437",
        "city": "Berlin",
        "district": "Pankow",
        "neighborhood": "Prenzlauer Berg",
    }


def test_reverse_result_rejects_foreign_coordinates() -> None:
    assert fields_from_reverse_result({"address": {"country_code": "pl"}}) == {}
