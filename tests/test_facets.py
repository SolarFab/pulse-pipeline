"""Facet detection tests (unify-taxonomy §2.4) — the spec's scenarios, verbatim."""

from pipeline.facets import detect_facets


def test_kid_friendly_food_market():
    e = {"title": "Streetfood Markt", "description": "Mit großem Kinderprogramm und Hüpfburg."}
    f = detect_facets(e)
    assert f["family_friendly"] is True


def test_open_air_cinema_is_outdoor():
    e = {"title": "Open-Air Kino im Volkspark", "description": "Filme unter freiem Himmel."}
    assert detect_facets(e)["outdoor"] is True


def test_free_entry_german_and_price_cents():
    assert detect_facets({"description": "Eintritt frei!"})["free_entry"] is True
    assert detect_facets({"title": "Gig", "price_cents": 0})["free_entry"] is True
    assert detect_facets({"title": "Gig", "price_cents": 1500})["free_entry"] is False


def test_no_signal_stays_false():
    e = {"title": "Konzert im Club", "description": "Live Musik am Abend.", "price": "15€"}
    assert detect_facets(e) == {
        "family_friendly": False,
        "outdoor": False,
        "free_entry": False,
    }


def test_adults_only_vetoes_family():
    e = {"title": "Kinky Karneval", "description": "Party ab 18 Jahren. Kinderleicht zu finden."}
    assert detect_facets(e)["family_friendly"] is False


def test_age_hint_counts_as_family():
    e = {"title": "Museumsführung", "description": "Für Kinder ab 6 Jahren geeignet."}
    assert detect_facets(e)["family_friendly"] is True
