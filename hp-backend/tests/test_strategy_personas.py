"""Rehearsing against a persona, without putting words in a real person's mouth.

Strategy Chat can now play a stakeholder so a seller can practise the pitch.
That is a feature built on top of the one rule this platform has never bent -
nothing is asserted that the account's own evidence does not support - and it
strains that rule harder than anything before it, because convincing dialogue
and grounded dialogue pull in opposite directions. A model makes a scene feel
real by adding operational colour: a refresh cycle, a frozen budget, a contract
term, a colleague who owns the decision. Every one of those is a fabrication a
seller might repeat in a real meeting.

So the properties pinned here are not "roleplay works". They are the four
guarantees that make it safe to ship:

**The menu is real people; absence is absence.** The roster comes from
`stakeholder_contacts_grid` and nothing else. An account with no contacts gets
no personas - never a default CISO, CIO or CTO, which is the fabrication that
got an earlier persona menu removed from Message Evaluator.

**The name is for the menu, the role is for the model.** The dropdown says
"Irvan Nr - Chief Operating Officer" because a seller prepares for a person.
The model is told only the role, and the validator refuses any reply naming
anyone on the roster. This is Message Evaluator's rule (`evaluator/sources.py`:
persona context may establish a role, "never what that person thinks, wants or
has said") applied to a feature that speaks in the first person.

**Voice is free, substance is sourced.** The user's instruction exactly: *"the
language of the person can be acc to the person but the things they say should
come/be infered from a source only."* Enforced per sentence, in Python.

**Isolation survives.** A persona id valid on one account does not resolve on
another, the same way an evidence id never did.

Run: python -m pytest tests/test_strategy_personas.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.strategy import chat, personas

ACCOUNT = "acct_under_test"
OTHER = "a_different_account"

CONTACTS = [
    {"contact_id": "c1", "full_name": "Irvan Nr", "title": "Chief Operating Officer",
     "normalized_department": "Information Technology", "seniority_band": "C-Suite",
     "influence_type": "Decision Maker", "hp_relevance_band": "high",
     "stakeholder_score": 90},
    {"contact_id": "c2", "full_name": "Stephen Dharma",
     "title": "Head of information technology project procurement",
     "normalized_department": "Information Technology", "seniority_band": "Director",
     "influence_type": "Budget Holder", "hp_relevance_band": "high",
     "stakeholder_score": 74},
    # No usable title - there is no role here to speak as.
    {"contact_id": "c3", "full_name": "Someone Else", "title": "Unknown",
     "stakeholder_score": 99},
]
TALKING = {"c1": {"pain_points": ["Tokenisation raises data security exposure"],
                  "decision_power": "Participates in IT infrastructure decisions",
                  "hp_play_focus": "Security / data protection"}}
CARDS = [
    {"area": "Device Management",
     "objection": "We are already using ManageEngine for device management",
     "counter_question": "How are you managing lifecycle today?",
     "likely_raiser": "Head of information technology project procurement"},
    {"area": "Endpoint Security", "objection": "Our endpoints are covered",
     "likely_raiser": "Endpoint Security"},
]


def _widgets(contacts=None, talking=None, cards=None, account_id=ACCOUNT):
    rows = []
    if contacts is not None:
        rows.append({"account_id": account_id, "widget_key": "stakeholder_contacts_grid",
                     "status": "available", "data": {"contacts": contacts}})
    if talking is not None:
        rows.append({"account_id": account_id, "widget_key": "stakeholder_talking_points",
                     "status": "available", "data": {"talking_points": talking}})
    if cards is not None:
        rows.append({"account_id": account_id, "widget_key": "objection_reframe_cards",
                     "status": "available", "data": {"cards": cards}})
    return rows


class _Collection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find_one(self, query):
        self.queries.append(query)
        return next((r for r in self.rows
                     if all(r.get(k) == v for k, v in query.items())), None)


class _Db:
    def __init__(self, rows):
        self.collection = _Collection(rows)

    def __getitem__(self, name):
        return self.collection


@pytest.fixture
def db(monkeypatch):
    def install(rows):
        database = _Db(rows)
        monkeypatch.setattr(personas, "get_db", lambda: database)
        return database
    return install


# --- the menu is real people --------------------------------------------

def test_the_menu_is_the_accounts_own_roster(db):
    db(_widgets(CONTACTS))
    found = personas.options(ACCOUNT)
    assert [row["name"] for row in found] == ["Irvan Nr", "Stephen Dharma"]
    assert [row["title"] for row in found] == [
        "Chief Operating Officer",
        "Head of information technology project procurement"]


def test_the_menu_is_ranked_by_the_stakeholder_maps_own_score(db):
    """Not a second opinion computed here - that feature already decided."""
    db(_widgets(CONTACTS))
    scores = [row["stakeholder_score"] for row in personas.options(ACCOUNT)]
    assert scores == sorted(scores, reverse=True)


def test_a_contact_with_no_usable_title_is_not_offered(db):
    """There is no role to play, so the dialogue would be the model's own."""
    db(_widgets(CONTACTS))
    assert "Someone Else" not in [row["name"] for row in personas.options(ACCOUNT)]


def test_an_account_with_no_contacts_gets_no_personas(db):
    """The fabrication that got the earlier persona menu removed.

    Offering a CISO to an account whose roster has none asserts an employment
    status the data does not support - and the archetypes were offered on every
    account alike, so they were never about the account at all.
    """
    db(_widgets([]))
    assert personas.options(ACCOUNT) == []
    db([])
    assert personas.options(ACCOUNT) == []


# --- isolation ------------------------------------------------------------

def test_a_persona_from_another_account_does_not_resolve(db):
    db(_widgets(CONTACTS) + _widgets(CONTACTS, account_id=OTHER))
    mine = personas.options(ACCOUNT)[0]["persona_id"]
    assert personas.resolve(ACCOUNT, mine) is not None
    # Same id, different account - the widget read is scoped, so it finds
    # nothing rather than finding someone else's person.
    installed = db(_widgets(CONTACTS, account_id=OTHER))
    assert personas.resolve(ACCOUNT, mine) is None
    for query in installed.collection.queries:
        assert query.get("account_id") == ACCOUNT


def test_an_unknown_persona_id_resolves_to_nothing(db):
    db(_widgets(CONTACTS))
    assert personas.resolve(ACCOUNT, "contact::not_a_person") is None
    assert personas.resolve(ACCOUNT, "") is None
    assert personas.resolve(ACCOUNT, None) is None


# --- the name is for the menu, the role is for the model ------------------

def test_the_menu_carries_the_name(db):
    """A seller preparing for a meeting is preparing for a person."""
    db(_widgets(CONTACTS))
    assert all(row["name"] for row in personas.options(ACCOUNT))


def test_the_name_never_reaches_the_model(db):
    """The single property this feature cannot ship without.

    A model given the name writes the name, and the transcript then reads as a
    real employee's quoted position on HP.
    """
    db(_widgets(CONTACTS, TALKING, CARDS))
    for row in personas.options(ACCOUNT):
        persona = personas.resolve(ACCOUNT, row["persona_id"])
        block = personas.prompt_block(persona).lower()
        assert persona["name"].lower() not in block
        for part in persona["name"].split():
            if len(part) > 3:
                assert part.lower() not in block, (
                    "%r leaked into the prompt" % part)
        assert persona["title"].lower() in block


def test_the_prompt_block_survives_being_formatted(db):
    """ROLEPLAY_SYSTEM goes through str.format; a stray brace would raise."""
    db(_widgets(CONTACTS, TALKING, CARDS))
    persona = personas.resolve(ACCOUNT, personas.options(ACCOUNT)[0]["persona_id"])
    rendered = chat.ROLEPLAY_SYSTEM.format(
        company="A Company", persona=personas.prompt_block(persona))
    assert "{" not in rendered and "}" not in rendered


# --- the persona's ammunition is Python's, not the model's ----------------

def test_objections_are_matched_by_the_playbooks_own_likely_raiser(db):
    """A lookup of a decision already made, not a new inference."""
    db(_widgets(CONTACTS, TALKING, CARDS))
    procurement = next(row for row in personas.options(ACCOUNT)
                       if row["title"].startswith("Head of information"))
    persona = personas.resolve(ACCOUNT, procurement["persona_id"])
    assert [card["area"] for card in persona["objections"]] == ["Device Management"]

    coo = personas.resolve(ACCOUNT, personas.options(ACCOUNT)[0]["persona_id"])
    assert coo["objections"] == [], "a card was attributed to the wrong role"


def test_a_persona_with_no_talking_points_carries_none(db):
    db(_widgets(CONTACTS, TALKING, CARDS))
    procurement = next(row for row in personas.options(ACCOUNT)
                       if row["title"].startswith("Head of information"))
    persona = personas.resolve(ACCOUNT, procurement["persona_id"])
    assert persona["pain_points"] == []
    assert persona["decision_power"] is None
    starters = personas.suggested_prompts(persona)
    assert starters, "a persona with no talking points still needs an opener"
    assert all(s["prompt_text"] for s in starters)


def test_every_roster_name_is_banned_not_just_the_persona(db):
    """"Talk to Stephen about it" names a real employee just as surely."""
    db(_widgets(CONTACTS))
    banned = personas.banned_names(ACCOUNT)
    assert "Irvan Nr" in banned
    assert "Stephen Dharma" in banned
    assert "Stephen" in banned and "Dharma" in banned


# ---------------------------------------------------------------------------
# Voice is free, substance is sourced
#
# The instruction, in the user's words: "the language of the person can be acc
# to the person but the things they say should come/be infered from a source
# only not anything according to their own."
#
# `_validate` cannot enforce that and these tests exist because it cannot. It
# needs ONE citation for a whole answer, so a persona could tag a sentence and
# invent three around it - none carrying a digit, so the figure check never sees
# them. And it treats anything that is not a refusal as asserting facts, so a
# persona could not say "go on" without being rejected three times.
# ---------------------------------------------------------------------------

PAYLOAD = (
    '===== objection_reframe_cards (feature: objection_playbook) =====\n'
    '{"objection":"We are already using ManageEngine for device management"}\n\n'
    '===== stakeholder_influence_map (feature: stakeholder_map) =====\n'
    '{"ranked_entry_path":[{"department":"Information Technology"}]}\n\n'
    '===== exec_key_metrics (feature: executive_dashboard) =====\n'
    '{"value_text":"IDR 323,392 billion","period":"FY2025"}'
)
KEYS = ["objection_reframe_cards", "stakeholder_influence_map", "exec_key_metrics"]
BANNED = ["Stephen Dharma", "Stephen", "Dharma", "Irvan Nr", "Irvan"]


def _gate(text):
    return chat._validate_roleplay(text, PAYLOAD, KEYS, BANNED)


def test_conversational_glue_needs_no_source():
    """The case that fails outright under the advisor's validator.

    "Hmm. Go on." asserts nothing, cites nothing, and is rejected by
    `_validate` as stating facts without evidence - three times, then an error.
    A persona that cannot say "go on" cannot hold a conversation.
    """
    ok, reason, cited, _ = _gate("Hmm. Go on.")
    assert ok is True, reason
    assert cited == []


def test_a_question_needs_no_source():
    """Asking is how this role finds out what is being proposed."""
    ok, reason, _, _ = _gate("So what exactly are you proposing to me?")
    assert ok is True, reason


def test_a_grounded_line_passes():
    ok, reason, cited, _ = _gate(
        "We are already using ManageEngine for device management here "
        "[objection_reframe_cards]. What would switching gain us?")
    assert ok is True, reason
    assert cited == ["objection_reframe_cards"]


def test_invented_operational_colour_is_rejected():
    """The failure this gate exists for, and the likeliest one.

    A contract term carries no digits, so the figure check cannot see it, and
    it sits beside a properly cited sentence, so the answer-level citation
    check is satisfied. Only a per-sentence rule catches it.
    """
    ok, reason, _, _ = _gate(
        "We are already using ManageEngine [objection_reframe_cards]. And we "
        "are locked into a three-year agreement with the incumbent until then.")
    assert ok is False
    assert "no source" in reason


def test_naming_any_real_person_is_rejected():
    """Not only the role being played - a colleague too."""
    ok, reason, _, _ = _gate(
        "That sits with Stephen Dharma, not me [stakeholder_influence_map].")
    assert ok is False
    assert "named a real person" in reason


def test_a_citation_that_does_not_support_the_sentence_is_rejected():
    """A tag proves the model asserted an attribution, not that it is true."""
    ok, reason, _, _ = _gate(
        "Our procurement freeze runs until the new fiscal year "
        "[exec_key_metrics].")
    assert ok is False
    assert "does not support" in reason


def test_roleplay_did_not_weaken_figure_grounding():
    """Pinned explicitly so a refactor cannot quietly drop it."""
    ok, reason, _, _ = _gate(
        "Our device spend fell 4271 percent last year [exec_key_metrics].")
    assert ok is False
    assert "4271" in reason


def test_a_section_that_is_not_in_this_account_is_rejected():
    ok, reason, _, _ = _gate(
        "We looked at that already [a_section_that_does_not_exist].")
    assert ok is False
    assert "a_section_that_does_not_exist" in reason


def test_a_speaker_label_is_stripped():
    """The one place the name could reappear after being kept from the model."""
    ok, reason, _, cleaned = _gate(
        "COO: We are already using ManageEngine for device management "
        "[objection_reframe_cards].")
    assert ok is True, reason
    assert not cleaned.startswith("COO:")
