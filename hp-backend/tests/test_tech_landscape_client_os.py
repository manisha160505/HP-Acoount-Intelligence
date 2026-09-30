"""The Client OS card: which spellings it sees, and what it says afterwards.

Reported against Advantest: the technographics export contains `Mac OS` and
the Technographic Map showed no Apple anywhere, while the "what it means for
HP" paragraph talked about Apple. Three defects in a row, and the first caused
the other two.

**The spelling.** The card's keyword list was `("apple", "macos", "ios")`, and
`_kw_in` matches a keyword literally between word boundaries over a merely
lowercased entry. `macos` therefore does not find `mac os` - the space is
fatal. The only Apple thing that did match was `"apple"` inside `"Apple iOS"`.

**The suppression that followed.** A card survives only if Driver 1 scores
above zero. `client_os` maps to no HP business category and an operating
system is given no HP play by design, so there is no HP opportunity for a
technology to be *related* to - the card needs a technology the rulebook names
outright. `"apple ios"` is named nowhere. `"mac os"` is: it is a WXP 04
technology worth a direct fit of 10. So the missing spelling was also the
missing score, and the card was deleted.

**The paragraph that outlived it.** The narrative runs before the filter -
deliberately, because Driver 1 needs the HP play the narrative writes - so it
described a vendor that was about to be removed, and the header kept counting
it.

The fix reads the spellings from `urgency.OS_FAMILIES`, which the urgency score
already uses on the same export and which already contains every one of them.
That is the point of these tests: not that `mac os` is in a list somewhere, but
that the two readers of that export cannot disagree about it again.

Run: python -m pytest tests/test_tech_landscape_client_os.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.dashboard.urgency import OS_FAMILIES
from app.services.extractors import tech_landscape as tl
from app.services.hp import tech_confidence as tc

# ---------------------------------------------------------------------------
# One table, not two
# ---------------------------------------------------------------------------

def test_the_card_reads_its_os_spellings_from_the_urgency_table():
    """The drift this bug was made of.

    The urgency score counted Apple on the same export the map could not see
    it in, because each kept its own list. Neither list is authoritative over
    the other, so there is only one.
    """
    assert OS_FAMILIES["windows"] == tl.CLIENT_OS_WINDOWS
    assert OS_FAMILIES["apple"] == tl.CLIENT_OS_APPLE
    assert set(OS_FAMILIES["linux"]) <= set(tl.CLIENT_OS_LINUX)


def test_the_linux_card_keeps_the_enterprise_unixes():
    """"Linux / Enterprise OS" describes itself as "Linux / Unix platform".

    `OS_FAMILIES` files unix, solaris and aix under `other`, beside ChromeOS
    and Android. Taking `OS_FAMILIES["linux"]` alone would have quietly cost an
    AIX or Solaris shop the card it has today, so those three are added back -
    and only those three: ChromeOS and Android are not Enterprise OS, and
    giving them a card of their own is a product decision, not a spelling fix.
    """
    assert set(tl.ENTERPRISE_UNIX) <= set(OS_FAMILIES["other"])
    assert set(tl.ENTERPRISE_UNIX) <= set(tl.CLIENT_OS_LINUX)
    assert "unix" in tl.CLIENT_OS_LINUX, "the list this replaced carried unix"
    for not_enterprise in ("android", "chromeos", "chrome os"):
        assert not_enterprise not in tl.CLIENT_OS_LINUX


# ---------------------------------------------------------------------------
# The spelling itself
# ---------------------------------------------------------------------------

def _matches(entry: str, keywords) -> bool:
    return any(tl._kw_in(kw, entry.lower()) for kw in keywords)


def test_mac_os_with_a_space_is_recognised_as_apple():
    """The reported bug, in one line."""
    assert _matches("Mac OS", tl.CLIENT_OS_APPLE)


def test_every_apple_spelling_an_export_uses_is_recognised():
    for entry in ("Mac OS", "macOS", "OS X", "osx", "Apple iOS", "iOS",
                  "iPadOS", "macOS Ventura"):
        assert _matches(entry, tl.CLIENT_OS_APPLE), entry


def test_the_boundary_rule_that_made_the_space_fatal_is_still_in_force():
    """The matcher is not loosened to fix this - the spelling is added.

    Substring matching is what put "Adobe Digital Marketing Suite" under
    Google Workspace. Widening `_kw_in` would have fixed Mac OS and brought
    that back, so the boundary stays and the list carries the spelling.
    """
    assert tl._kw_in("mac os", "mac os") is True
    assert tl._kw_in("macos", "mac os") is False
    assert tl._kw_in("ios", "kiosk software") is False
    assert tl._kw_in("windows", "windows 11 pro") is True


def test_windows_and_linux_are_unaffected():
    assert _matches("Microsoft Windows 10", tl.CLIENT_OS_WINDOWS)
    assert _matches("CentOS", tl.CLIENT_OS_LINUX)
    assert _matches("Red Hat Enterprise Linux", tl.CLIENT_OS_LINUX)
    assert not _matches("Mac OS", tl.CLIENT_OS_WINDOWS)


# ---------------------------------------------------------------------------
# The score that decides whether the card survives
# ---------------------------------------------------------------------------

def test_mac_os_carries_the_card_through_the_driver_one_gate():
    """The spelling fix IS the suppression fix, and nothing was invented.

    No HP relevance is added for Apple and no rulebook row is touched: "mac
    os" was already a named WXP 04 technology. It simply never reached the
    scorer, because the card never put it in `detected_as`.
    """
    points, basis, matched = tc.driver_1_for_card(
        ["Apple iOS", "Mac OS"], None, None)
    assert points == 10
    assert matched["rule"] == "WXP 04"
    assert tc.is_publishable(points) is True
    assert "mac os" in basis.lower()


def test_apple_ios_alone_is_still_suppressed():
    """Known residue, pinned deliberately rather than quietly widened.

    An account with iOS and no Mac OS still loses the card: `ios` is named in
    no rulebook rule. Adding it would be a scoring change, and scoring is the
    client's. This test exists so that stays a decision rather than a drift.
    """
    points, _basis, matched = tc.driver_1_for_card(["Apple iOS"], None, None)
    assert points == 0
    assert matched is None
    assert tc.is_publishable(points) is False


def test_client_os_remains_contextual_with_no_risk_label():
    """F7, upheld: HP has no line in this category, so no risk is rated.

    Surviving the gate is not the same as being an opportunity. The category
    is badged contextual, and the badge is what decides the risk label - so a
    published Apple card carries none.
    """
    short, _long, risk = tl.RELATIONSHIP_BY_BADGE["contextual - no direct hp line"]
    assert short == "Contextual"
    assert risk is None
    assert tc.hp_category_for("client_os") is None


# ---------------------------------------------------------------------------
# What the card says once the filter has run
# ---------------------------------------------------------------------------

def _categories(what_it_means, vendors):
    return [{"category_key": "client_os", "category_name": "Client OS",
             "detected_signals_count": 2, "what_it_means": what_it_means,
             "hp_relationship": "Contextual - no direct HP line in this category",
             "vendors": vendors}]


SUPPRESSED_APPLE = [{"category": "client_os", "vendor": "Apple",
                     "reason": "the rulebook connects apple ios to no HP "
                               "opportunity in this category"}]


def test_the_header_count_matches_the_cards_that_survived():
    """It read "2 detected signals" above one card."""
    categories = _categories("Windows dominates the estate.",
                             [{"vendor_name": "Microsoft"}])
    report = tl._reconcile_after_suppression(categories, SUPPRESSED_APPLE)
    assert categories[0]["detected_signals_count"] == 1
    assert report["recounted"] == [
        {"category": "client_os", "was": 2, "now": 1}]


def test_whitespace_rows_are_not_counted_as_detected_signals():
    """They are HP's own absence, which is what the original counts excluded."""
    categories = _categories(None, [{"vendor_name": "Microsoft"},
                                    {"vendor_name": "HP", "is_whitespace": True}])
    tl._reconcile_after_suppression(categories, [])
    assert categories[0]["detected_signals_count"] == 1


def test_a_narrative_naming_a_suppressed_vendor_is_dropped():
    """The text and the cards must not disagree in front of a seller."""
    categories = _categories(
        "Apple devices sit alongside Windows across the estate.",
        [{"vendor_name": "Microsoft"}])
    report = tl._reconcile_after_suppression(categories, SUPPRESSED_APPLE)
    assert categories[0]["what_it_means"] is None
    assert report["narratives_dropped"] == [
        {"category": "client_os", "named": ["Apple"]}]


def test_a_narrative_naming_only_surviving_vendors_is_left_alone():
    """The check is targeted; it does not clear every paragraph on sight."""
    text = "Windows is the standard build across the estate."
    categories = _categories(text, [{"vendor_name": "Microsoft"}])
    report = tl._reconcile_after_suppression(categories, SUPPRESSED_APPLE)
    assert categories[0]["what_it_means"] == text
    assert report["narratives_dropped"] == []


def test_a_vendor_name_inside_a_longer_word_does_not_drop_the_narrative():
    """Same boundary rule as the keyword matcher - one matcher, one behaviour."""
    text = "Dell Technologies supplies the estate."
    categories = _categories(text, [{"vendor_name": "Dell"}])
    report = tl._reconcile_after_suppression(
        categories, [{"category": "client_os", "vendor": "HP"}])
    assert categories[0]["what_it_means"] == text
    assert report["narratives_dropped"] == []


def test_nothing_suppressed_changes_nothing():
    text = "Windows and Apple both appear in the estate."
    categories = _categories(text, [{"vendor_name": "Microsoft"},
                                    {"vendor_name": "Apple"}])
    report = tl._reconcile_after_suppression(categories, [])
    assert categories[0]["what_it_means"] == text
    assert categories[0]["detected_signals_count"] == 2
    assert report == {"recounted": [], "narratives_dropped": []}
