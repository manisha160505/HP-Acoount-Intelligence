"""Dictionary behaviour for intent-map-v2.

v2 widened the vocabulary and added the four context themes. These pin the
rules that keep the widening conservative: a context theme never carries an HP
category, the non-hardware guard still holds, and an ambiguous topic is still
flagged rather than placed.
"""
import pytest

from app.services.hp import intent_topic_map as tm


@pytest.mark.parametrize("topic,theme", [
    ("machine learning & artificial intelligence: ai strategy", tm.THEME_AI),
    ("technology: chatgpt", tm.THEME_AI),
    ("hardware: ai chips", tm.THEME_AI),
    ("servers: linux servers", tm.THEME_CLOUD),
    ("data center: data center optimization", tm.THEME_CLOUD),
    ("technology: microsoft azure", tm.THEME_CLOUD),
    ("security: anti spam", tm.THEME_SECURITY),
    ("other: cyber essentials (ce)", tm.THEME_SECURITY),
    ("privacy: tokenization", tm.THEME_FINANCE),
    ("trading & investing: hedge funds", tm.THEME_FINANCE),
    ("supply chain: door-to-airport", tm.THEME_COMMERCE),
    ("transportation: cargo trucks & trailers", tm.THEME_COMMERCE),
    ("staff administration: staffing", tm.THEME_COLLAB),
    ("policy & culture: flexible working", tm.THEME_COLLAB),
    ("telecommunications: phone system", tm.THEME_COLLAB),
    ("hardware: monitors", tm.THEME_DEVICES),
    ("personal computer: 2-in-1 pcs", tm.THEME_DEVICES),
])
def test_topic_lands_in_expected_theme(topic, theme):
    assert tm.map_topic(topic)["theme"] == theme


@pytest.mark.parametrize("topic", [
    "servers: linux servers",
    "security: anti spam",
    "privacy: tokenization",
    "supply chain: door-to-airport",
])
def test_context_themes_never_carry_an_hp_category(topic):
    """A context theme describes research, it does not name an HP line."""
    result = tm.map_topic(topic)
    assert result["theme"] in tm.CONTEXT_THEMES
    assert result["hp_category"] is None


def test_hr_topic_is_workplace_but_not_a_poly_signal():
    """Workplace topics join Collaboration without becoming hardware demand."""
    result = tm.map_topic("recruitment, hiring & onboarding: talent acquisition")
    assert result["theme"] == tm.THEME_COLLAB
    assert result["hp_category"] is None


def test_meeting_room_still_maps_to_poly():
    assert tm.map_topic("hardware: meeting room systems")["hp_category"] == tm.CAT_POLY


def test_non_hardware_qualifier_still_blocks_a_device_signal():
    """The v1 guard survives: 'pc' next to 'software' is not device demand."""
    result = tm.map_topic("other: ais software for pc")
    assert result["theme"] == tm.THEME_OTHER
    assert result["mapping_status"] == "flagged"
    assert result["hp_category"] is None


def test_precedence_resolves_an_hp_theme_over_a_context_theme():
    result = tm.map_topic("security: cloud security")
    assert result["theme"] == tm.THEME_SECURITY
    assert result["mapping_status"] == "mapped"


def test_precedence_never_carries_a_category_from_the_losing_theme():
    """The winning theme's own terms decide the category."""
    result = tm.map_topic("cloud printing for servers")
    assert result["theme"] == tm.THEME_PRINT
    assert result["hp_category"] == tm.CAT_PRINT


def test_two_hp_categories_keep_the_theme_but_get_no_category():
    result = tm.map_topic("pc and workstation refresh")
    assert result["theme"] == tm.THEME_DEVICES
    assert result["hp_category"] is None
    assert result["mapping_status"] == "flagged"


def test_genuine_noise_stays_out_of_every_theme():
    for topic in ("general: pets", "general: astronomy", "general: jewelry"):
        assert tm.map_topic(topic)["theme"] == tm.THEME_OTHER


def test_other_bucket_is_last_in_display_order():
    assert tm.THEMES[-1] == tm.THEME_OTHER
    assert tm.THEME_OTHER == "Other / Low Relevance"


def test_every_term_names_a_known_theme_and_category():
    for term, (theme, category) in tm.TERMS.items():
        assert theme in tm.THEMES, term
        assert category is None or category in {c["category"] for c in tm.HP_CATEGORIES}, term


def test_every_theme_is_ranked_for_precedence():
    """A theme missing from precedence would raise on an ambiguous topic."""
    for theme in tm.THEMES:
        if theme != tm.THEME_OTHER:
            assert theme in tm.THEME_PRECEDENCE
