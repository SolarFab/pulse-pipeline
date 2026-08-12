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
