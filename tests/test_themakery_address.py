"""The Makery is a marketplace: each workshop runs at a different partner studio,
and every detail page carries the platform's own footer address as well.

The old extractor ran a regex over raw HTML and forbade `<` between street and
postcode — but they sit in separate elements, so it matched nothing, `address`
stayed None, and the geocoder fell back to the venue name "The Makery". Every
event landed on the head office in Prenzlauer Berg while their neighborhoods
spanned 46 districts. These tests pin the two properties that
failure needed: parse text rather than markup, and never take the footer.
"""

from __future__ import annotations

from scrapers.venues.themakery import extract_studio_address as extract

# Footer first, studio second — the order on the real page varies, and the
# extractor must not depend on it.
PAGE = """<html><body>
  <footer>
    <div>the Makery</div>
    <div>John-Schehr-Strasse 2</div>
    <div>10407 Berlin</div>
    <div>Prenzlauer Berg</div>
  </footer>
  <section class="host">
    <h3>PLÖTTJES STUDIO</h3>
    <div>Schleiermacherstraße 18</div>
    <div>10961 Berlin</div>
    <div>Kreuzberg</div>
    <a href="/route">Route</a>
  </section>
</body></html>"""


def test_takes_the_studio_not_the_platform_footer():
    assert extract(PAGE) == "Schleiermacherstraße 18, 10961 Berlin"


def test_street_and_postcode_may_live_in_separate_elements():
    """The exact shape the old raw-HTML regex could not match: `<` between them."""
    assert "</div>" in PAGE.split("Schleiermacherstraße 18")[1].split("10961")[0]
    assert extract(PAGE) is not None


def test_studio_before_footer_still_resolves():
    reordered = PAGE.replace("<footer>", "<!--").replace("</footer>", "-->")
    assert extract(reordered) == "Schleiermacherstraße 18, 10961 Berlin"


def test_footer_only_page_yields_nothing_rather_than_the_head_office():
    """A page with no studio block must return None. Returning the platform address
    is what produced 722 events on one pin — silence is the safer failure."""
    footer_only = """<html><body><footer>
        <div>the Makery</div><div>John-Schehr-Strasse 2</div>
        <div>10407 Berlin</div></footer></body></html>"""
    assert extract(footer_only) is None


def test_a_studio_that_happens_to_sit_in_10407_is_still_accepted():
    """The footer is skipped by STREET, not by postcode: real partner studios do
    exist in Prenzlauer Berg, and excluding the district would drop them."""
    page = """<html><body>
        <footer><div>the Makery</div><div>John-Schehr-Strasse 2</div>
        <div>10407 Berlin</div></footer>
        <section><h3>Ateliers</h3><div>Storkowerstrasse 115</div>
        <div>10407 Berlin</div></section></body></html>"""
    assert extract(page) == "Storkowerstrasse 115, 10407 Berlin"


# --- Street normalisation ------------------------------------------------------
#
# Every string below is a real value the marketplace produced. Concatenated
# unchanged with ", <plz> Berlin" they yield addresses no geocoder accepts; the
# geocode then failed and the event silently inherited the venue's coordinates,
# putting Neukoelln workshops on the platform's Prenzlauer Berg pin.

import pytest  # noqa: E402

from scrapers.venues.themakery import clean_street  # noqa: E402


@pytest.mark.parametrize(
    "raw,expected",
    [
        # postcode and house number repeated after the street
        ("Reuterstraße 82, 12053 82", "Reuterstraße 82"),
        # city and country interleaved, house number orphaned at the end
        ("Reuterstraße , Berlin, Allemagne 82", "Reuterstraße 82"),
        # house number repeated
        ("Wrangelstrasse 31a 31a", "Wrangelstrasse 31a"),
        # double space
        ("Golzstraße  32", "Golzstraße 32"),
        ("Storkowerstrasse  115", "Storkowerstrasse 115"),
        # legitimate shapes must survive untouched
        ("Moosdorferstrasse 7-9", "Moosdorferstrasse 7-9"),
        ("Gerichstr. 12-13", "Gerichstr. 12-13"),
        ("Markgrafendamm 24, Haus 18", "Markgrafendamm 24, Haus 18"),
        ("Schleiermacherstraße 18", "Schleiermacherstraße 18"),
    ],
)
def test_clean_street_normalises_real_marketplace_values(raw, expected):
    assert clean_street(raw) == expected


@pytest.mark.parametrize("raw", ["", "Route", "Kreuzberg", "12053", "PLÖTTJES STUDIO"])
def test_clean_street_rejects_lines_that_are_not_streets(raw):
    """None means 'no address', which is recoverable. A wrong address is not:
    it geocodes to somewhere real and nothing downstream can tell it is wrong."""
    assert clean_street(raw) is None


def test_a_malformed_street_yields_no_address_rather_than_a_wrong_one():
    page = """<html><body>
        <section><h3>Studio</h3><div>Kreuzberg</div>
        <div>12053 Berlin</div></section></body></html>"""
    assert extract(page) is None


def test_the_reuterstrasse_workshops_now_resolve_to_neukoelln():
    """The two events Fabian found pinned in Prenzlauer Berg."""
    page = """<html><body>
        <footer><div>the Makery</div><div>John-Schehr-Strasse 2</div>
        <div>10407 Berlin</div></footer>
        <section><h3>Studio</h3><div>Reuterstraße 82, 12053 82</div>
        <div>12053 Berlin</div></section></body></html>"""
    assert extract(page) == "Reuterstraße 82, 12053 Berlin"
