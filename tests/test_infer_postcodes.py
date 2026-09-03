"""Postcode inference: the guard, not the arithmetic.

A postcode decides which Kiez an event appears in, so a wrong one is worse than a
missing one — missing degrades to a wider search, wrong sends someone across town.
These pin the cases where the inference must REFUSE to answer.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "inf", ROOT / "scripts" / "infer_missing_postcodes.py"
)
inf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inf)

# Prenzlauer Berg, near Helmholtzplatz
HERE = (52.5400, 13.4180)


def near(n: int, plz: str, offset: float = 0.001) -> list[dict]:
    return [{"lat": HERE[0] + i * offset, "lng": HERE[1], "postal_code": plz} for i in range(n)]


def test_agreeing_close_neighbours_decide_it():
    plz, agreement, dist = inf.infer(*HERE, near(7, "10437"))
    assert plz == "10437"
    assert agreement == 1.0
    assert dist < 0.2


def test_disagreeing_neighbours_yield_nothing():
    """A boundary venue: half one Kiez, half another. Guessing sends someone
    across a border they cared about."""
    mixed = near(4, "10437") + [
        {"lat": HERE[0] + 0.001 * i, "lng": HERE[1] + 0.0005, "postal_code": "10405"}
        for i in range(4)
    ]
    plz, agreement, _ = inf.infer(*HERE, mixed)
    assert plz is None
    assert agreement < inf.MIN_AGREEMENT


def test_distant_neighbours_are_not_evidence():
    """Unanimous but 5 km away is not evidence about this point — Berlin postcode
    areas are small, so distance is the binding constraint, not agreement."""
    far = [{"lat": HERE[0] + 0.05, "lng": HERE[1] + 0.05, "postal_code": "10999"}] * 7
    plz, _, dist = inf.infer(*HERE, far)
    assert plz is None
    assert dist > inf.MAX_NEIGHBOUR_KM


def test_no_neighbours_at_all_is_not_an_error():
    plz, _, _ = inf.infer(*HERE, [])
    assert plz is None


def test_a_clear_majority_is_enough():
    """Real data is never unanimous; requiring it would refuse almost everything."""
    mostly = near(6, "10437") + [{"lat": HERE[0], "lng": HERE[1] + 0.0004, "postal_code": "10405"}]
    plz, agreement, _ = inf.infer(*HERE, mostly)
    assert plz == "10437"
    assert agreement >= inf.MIN_AGREEMENT


def test_haversine_matches_a_known_distance():
    # Brandenburger Tor -> Alexanderplatz is roughly 2.7 km
    d = inf.haversine_km(52.5163, 13.3777, 52.5219, 13.4132)
    assert 2.3 < d < 3.1


def test_the_thresholds_are_conservative():
    """If these drift loose, the script starts inventing Kieze."""
    assert inf.MIN_AGREEMENT >= 0.6
    assert inf.MAX_NEIGHBOUR_KM <= 2.0


def test_one_close_neighbour_is_not_a_majority():
    """The hole the review found: agreement divided by however many happened to be
    close, so a single close neighbour scored 100% and decided the Kiez alone."""
    one_close_six_far = [{"lat": HERE[0], "lng": HERE[1] + 0.0005, "postal_code": "10437"}] + [
        {"lat": HERE[0] + 0.05, "lng": HERE[1] + 0.05, "postal_code": "10999"}
    ] * 6
    plz, agreement, _ = inf.infer(*HERE, one_close_six_far)
    assert plz is None
    assert agreement < 1.0, "a lone neighbour must not read as unanimous"


def test_support_is_counted_against_the_full_neighbour_set():
    """Two close and agreeing is still only 2 of 7 — not enough to name a Kiez."""
    two_close = (
        near(2, "10437") + [{"lat": HERE[0] + 0.05, "lng": HERE[1], "postal_code": "10999"}] * 5
    )
    assert inf.infer(*HERE, two_close)[0] is None


def test_five_close_and_agreeing_is_enough():
    five = near(5, "10437") + [{"lat": HERE[0] + 0.05, "lng": HERE[1], "postal_code": "10999"}] * 2
    plz, agreement, _ = inf.infer(*HERE, five)
    assert plz == "10437"
    assert agreement >= inf.MIN_AGREEMENT


def test_min_support_is_a_real_majority_of_the_sample():
    assert inf.MIN_SUPPORT >= inf.NEIGHBOURS * inf.MIN_AGREEMENT
