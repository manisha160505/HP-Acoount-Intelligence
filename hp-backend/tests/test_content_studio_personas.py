"""Every persona kind must reach the model, and only a person may be named.

Content Studio offers four kinds of persona and each one changes what the model
is told: which fields it sees, which rule it is held to, whether it may write a
name, and how the email opens. A fourth kind (`client_role`, the client's own
buying committee) was added without teaching those four places about it, and
nothing failed until a seller clicked Generate - the whole path is on demand, so
no extractor run and no test touched it. `_build_system_prompt` raised
`KeyError: 'client_role'` on an endpoint that catches only ValueError.

So the first test here is the dull one that would have caught it: every kind
builds a prompt. The rest pin the distinction the kinds exist for.

Run: python -m pytest tests/test_content_studio_personas.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import content_studio as cs

NAMED = {
    "id": "contact_1", "kind": "named", "source": "Source A",
    "title": "Chief Information Officer", "full_name": "Mike Higgins",
    "department": "Executive", "seniority": "C-Suite",
    "influence_type": "Decision Maker",
    "buying_committee_persona": "IT Decision Maker",
}
# The client's eight, keyed by the specification's persona_id. A client_role
# persona now carries one of those ids, so the evidence block is built from
# the hardcoded pack rather than from whatever the export happened to say.
CLIENT_FILLED = {
    "id": "vp-it", "kind": "client_role", "source": "company_personas",
    "title": "VP / Head of Information Technology", "subtitle": "Adam Neal",
    "department": "IT",
    "buying_committee_persona": "Economic Buyer",
    "full_name": "Adam Neal", "actual_job_title": "Head of IT",
    "contact_status": "Work email only; phone missing", "is_filled": True,
}
CLIENT_EMPTY = {
    "id": "head-procurement", "kind": "client_role",
    "source": "company_personas", "title": "Head of Procurement",
    "subtitle": "Procurement", "department": "Procurement",
    "buying_committee_persona": "Gatekeeper - Procurement & Legal",
    "full_name": None,
    "contact_status": "No suitable distinct candidate found", "is_filled": False,
}
ROLE_PROXY = {
    "id": "role_it_manager", "kind": "role_proxy", "source": "job_openings",
    "title": "Information Technology — Manager",
    "department": "Information Technology", "seniority": "Manager",
    "posting_count": 3, "source_titles": ["IT Manager", "Network Manager"],
}
ARCHETYPE = cs.ARCHETYPE_PERSONAS[0]
EVERY_KIND = [NAMED, CLIENT_FILLED, CLIENT_EMPTY, ROLE_PROXY, ARCHETYPE]


def _block(persona):
    text, _labels = cs._label_block("P", cs._persona_evidence(persona))
    return text


def _prompt(persona, content_type="email"):
    contract = cs.CONTENT_TYPE_CONTRACTS[content_type]
    return cs._build_system_prompt(
        "ACME Corp", contract, "[A1] Industry: Manufacturing", persona,
        _block(persona), "device refresh", "", "", "")


class TestEveryKindReachesTheModel:

    def test_every_persona_kind_builds_a_prompt(self):
        """The test that was missing. A kind the prompt layer does not know is
        a 500 on an endpoint a seller clicks."""
        for persona in EVERY_KIND:
            assert "TARGET PERSONA" in _prompt(persona), persona["kind"]

    def test_every_kind_has_a_header(self):
        for persona in EVERY_KIND:
            assert cs._persona_header(persona).strip()

    def test_an_unknown_kind_falls_back_rather_than_raising(self):
        """A kind added in future should degrade to the most cautious header,
        not take the endpoint down while someone notices."""
        assert cs._persona_header({"kind": "something_new"}) == \
            cs.PERSONA_KIND_HEADERS["archetype"]


class TestWhatCountsAsAPerson:

    def test_a_named_contact_is_a_person(self):
        assert cs._is_named_person(NAMED) is True

    def test_a_filled_client_role_is_a_person(self):
        """The client told us who holds it, so it is that person."""
        assert cs._is_named_person(CLIENT_FILLED) is True

    def test_an_unfilled_client_role_is_a_role(self):
        assert cs._is_named_person(CLIENT_EMPTY) is False

    def test_a_hiring_proxy_is_a_role(self):
        assert cs._is_named_person(ROLE_PROXY) is False

    def test_an_archetype_is_a_role(self):
        assert cs._is_named_person(ARCHETYPE) is False


class TestTheClientRoleBlock:

    def test_a_filled_role_carries_the_contact(self):
        block = _block(CLIENT_FILLED)
        assert "Name: Adam Neal" in block
        assert "Actual job title: Head of IT" in block
        assert "Buying-committee angle: Economic Buyer" in block

    def test_an_unfilled_role_carries_no_name(self):
        """[P6] and [P7] are omitted entirely, not emitted empty. The
        specification is explicit that an empty slot invites the model to
        fill it."""
        block = _block(CLIENT_EMPTY)
        assert "Adam Neal" not in block
        assert "Name:" not in block
        assert "Actual job title" not in block

    def test_the_unfilled_state_is_carried_by_the_rule_not_the_evidence(self):
        """Spec Section 3.3 closes slot 2 at [P1]-[P5] plus the contact.

        The gap reason used to sit in the evidence block. It moved: the fact
        that nobody holds this role is a constraint on what may be written,
        not a fact about the account, so it belongs in the persona RULE where
        the model is bound by it - "Name nobody. Greet nobody by name."
        """
        assert "No suitable distinct candidate found" not in _block(CLIENT_EMPTY)
        rule = cs._persona_rule("client_role", "ACME Corp",
                                cs.CONTENT_TYPE_CONTRACTS["email"], False)
        assert "NO PERSON HAS BEEN IDENTIFIED" in rule.upper()
        assert "may not name anyone" in rule.lower()

    def test_each_field_is_its_own_citable_line(self):
        """Flattened into one Description blob, department and angle could not
        be cited under rule 7 and the validator could not see the name."""
        lines = _block(CLIENT_FILLED).splitlines()
        # [P1] role, [P2] department, [P3] angle, [P4] remit, [P5] metrics,
        # then [P6] name and [P7] actual title because this one is filled.
        assert len(lines) == 7
        assert all(line.startswith("[P") for line in lines)


class TestTheRuleEachKindIsHeldTo:

    def test_a_filled_role_is_written_to_as_a_person(self):
        prompt = _prompt(CLIENT_FILLED)
        assert "THE CLIENT HAS NAMED THE PERSON IN IT" in prompt
        assert "never" in prompt.lower()

    def test_every_angle_the_data_carries_is_named_in_the_rule(self):
        """The client supplies five, and 14 of the 32 roles on an account are
        the two that used to fall through to "none supplied": Gatekeeper and
        Finance - Budget Owner."""
        prompt = _prompt(CLIENT_FILLED)
        for angle in ("Economic Buyer", "Technical Buyer", "Finance - Budget Owner",
                      "Gatekeeper - Procurement & Legal",
                      "Influencer / Line-of-Business Champion"):
            assert angle in prompt, angle

    def test_a_gatekeeper_is_never_pitched_a_product(self):
        assert "never pitch a product to them" in _prompt(CLIENT_FILLED)

    def test_a_budget_owner_is_never_quoted_a_price(self):
        assert "never quote a price or discount" in _prompt(CLIENT_FILLED)

    def test_an_unfilled_role_may_not_name_anyone(self):
        prompt = _prompt(CLIENT_EMPTY)
        assert "NO PERSON HAS BEEN IDENTIFIED" in prompt
        assert "may NOT name anyone" in prompt

    def test_a_client_role_is_never_told_the_role_does_not_exist(self):
        """The archetype rule says "Do NOT claim the role exists" - which is
        false for a role the client named as a target at this account."""
        for persona in (CLIENT_FILLED, CLIENT_EMPTY):
            assert "Do NOT claim the role exists" not in _prompt(persona)

    def test_a_public_post_outranks_every_kind(self):
        for persona in EVERY_KIND:
            prompt = _prompt(persona, "linkedin")
            assert "THIS IS A PUBLIC POST" in prompt
            assert "Never name, address or describe an individual" in prompt


class TestWhoMayBeNamedInTheCopy:
    """`_validate_asset` rejects copy naming a contact unless the target IS
    that person. The gate reads the same predicate the prompt does."""

    def test_a_role_type_may_not_name_a_contact(self):
        for persona in (CLIENT_EMPTY, ROLE_PROXY, ARCHETYPE):
            assert not cs._is_named_person(persona)

    def test_a_filled_client_role_may_use_its_own_contact(self):
        assert cs._is_named_person(CLIENT_FILLED)


class TestTheGreeting:

    def test_a_filled_client_role_is_greeted_by_first_name(self):
        assert cs._compose_greeting(
            CLIENT_FILLED, cs.CONTENT_TYPE_CONTRACTS["email"]) == "Dear Adam,"

    def test_an_unfilled_client_role_gets_a_role_placeholder(self):
        greeting = cs._compose_greeting(
            CLIENT_EMPTY, cs.CONTENT_TYPE_CONTRACTS["email"])
        assert greeting == "Dear [Head of Procurement Name],"

    def test_a_branded_emailer_greets_the_role_itself(self):
        greeting = cs._compose_greeting(
            CLIENT_EMPTY, cs.CONTENT_TYPE_CONTRACTS["branded_emailer"])
        assert greeting == "Dear Head of Procurement,"


class TestTheHiringProxyBlock:

    def test_an_empty_seniority_is_left_out(self):
        """"[P3] Seniority: " with nothing after it is a line the model can
        cite and learn nothing from."""
        block = _block(dict(ROLE_PROXY, seniority=""))
        assert "Seniority:" not in block
        assert "Open postings: 3 postings" in block

    def test_a_seniority_that_exists_is_shown(self):
        assert "Seniority: Manager" in _block(ROLE_PROXY)
