"""Who the seller can rehearse against, built from the account's own roster.

Strategy Chat has two modes. The advisor answers questions about the account.
The roleplay persona lets a seller practise the conversation itself - pitch, get
pushback, find out where the story breaks before it breaks in front of a
customer.

**The menu is the account's real people, or it is empty.** An earlier attempt at
this shipped five hardcoded archetypes - "CIO / IT Leadership", "Security
Leadership (Wolf Security)" - two of which attached real Astra names to
departments that appear nowhere in the account, and all of which were offered on
every other account too. Astra has no CISO, no CIO and no CTO; a menu offering
them asserts employment the data does not support. So this reads
`stakeholder_contacts_grid` and nothing else, and an account with no contacts
gets no personas rather than a default set.

**The name is for the menu. The role is for the model.** The dropdown reads
"Irvan Nr - Chief Operating Officer", because a seller preparing for a meeting
is preparing for a person. What the model is told is the ROLE - title,
department, seniority, influence - and never the name. Message Evaluator settled
this rule first and enforces it in Python (`evaluator/sources.py`: persona
context "may establish the contact's role, department, seniority / never what
that person thinks, wants or has said"; `evaluator/verify.py:guard_reaction`
withholds output that names or quotes a contact). Two features disagreeing about
whether a real employee can be put words into would be worse than either rule.

The Objection Playbook already carries the same disclaimer for the same reason:
*"Anticipated objections a seller should be ready for ... Not statements made by
any contact."*

**Nothing here is generated.** The persona's concerns are the contact's own
`pain_points` from Stakeholder Map, and its objections are the cards whose
`likely_raiser` Python already matched to this contact's title. The model
supplies the voice; every substantive thing the voice says is in the payload
before the conversation starts.
"""

import logging

from app.database.mongodb import get_db

logger = logging.getLogger(__name__)

# Matches Message Evaluator's scheme (`message_evaluator.py`), so a persona id
# means the same thing in both features.
PERSONA_PREFIX = "contact::"

# A title too generic to rehearse against. Speaking as "Employee" tells the
# model nothing the account data does not already say, and the resulting
# dialogue is the model's own invention rather than the role's.
_UNUSABLE_TITLE = frozenset({
    "", "-", "n/a", "na", "none", "employee", "staff", "member", "unknown",
})


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _widget(account_id: str, widget_key: str) -> dict:
    """One published widget's data, scoped to this account, or {}."""
    found = get_db()["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": widget_key})
    if not found or found.get("status") != "available":
        return {}
    return found.get("data") or {}


def _contacts(account_id: str) -> list:
    return _widget(account_id, "stakeholder_contacts_grid").get("contacts") or []


def options(account_id: str) -> list:
    """The dropdown, best-scored first.

    `stakeholder_score` is the Stakeholder Map's own ranking - seniority,
    department relevance and HP fit already weighed - so the seller is offered
    the people that feature already decided matter, in that order, rather than
    a second opinion computed here.
    """
    found = []
    for contact in _contacts(account_id):
        title = _text(contact.get("title"))
        contact_id = _text(contact.get("contact_id"))
        if not contact_id or title.lower() in _UNUSABLE_TITLE:
            continue
        found.append({
            "persona_id": PERSONA_PREFIX + contact_id,
            # For the menu only. Never sent to the model - see `prompt_block`.
            "name": _text(contact.get("full_name")) or None,
            "title": title,
            "department": _text(contact.get("normalized_department")) or None,
            "seniority_band": _text(contact.get("seniority_band")) or None,
            "influence_type": _text(contact.get("influence_type")) or None,
            "hp_relevance_band": _text(contact.get("hp_relevance_band")) or None,
            "stakeholder_score": contact.get("stakeholder_score"),
        })
    found.sort(key=lambda row: -(row.get("stakeholder_score") or 0))
    return found


def _matching_objections(account_id: str, title: str) -> list:
    """The objection cards this role is the likely raiser of.

    `likely_raiser` is set by the Objection Playbook from `prospect_contacts` -
    it holds a contact's TITLE, matched there, not here. Comparing titles is
    therefore a lookup of a decision Python already made, not a new inference.
    """
    if not title:
        return []
    wanted = title.strip().lower()
    cards = _widget(account_id, "objection_reframe_cards").get("cards") or []
    return [{
        "area": _text(card.get("area")),
        "objection": _text(card.get("objection")),
        "counter_question": _text(card.get("counter_question")),
        "detected_vendors": card.get("detected_vendors") or [],
    } for card in cards
        if _text(card.get("likely_raiser")).strip().lower() == wanted]


def resolve(account_id: str, persona_id: str) -> dict | None:
    """One persona, or None when it does not belong to this account.

    None rather than a raise, and scoped rather than looked up globally: a
    `persona_id` from another account must not resolve here, the same way an
    evidence id from another account never resolved under the retrieval design.
    """
    wanted = _text(persona_id)
    if not wanted:
        return None
    chosen = next((row for row in options(account_id)
                   if row["persona_id"] == wanted), None)
    if not chosen:
        logger.info("strategy chat: persona %s does not belong to account %s",
                    wanted, account_id)
        return None

    contact_id = wanted[len(PERSONA_PREFIX):]
    points = (_widget(account_id, "stakeholder_talking_points")
              .get("talking_points") or {}).get(contact_id) or {}

    return {
        **chosen,
        # The contact's own, from Stakeholder Map - not written here.
        "pain_points": points.get("pain_points") or [],
        "decision_power": _text(points.get("decision_power")) or None,
        "hp_play_focus": _text(points.get("hp_play_focus")) or None,
        "objections": _matching_objections(account_id, chosen["title"]),
    }


def banned_names(account_id: str) -> list:
    """Every real person on this roster, for the validator to refuse to say.

    Not just the persona being played. "Talk to Budi about it" puts words about
    a named employee into a simulated conversation exactly as surely as signing
    the reply with that name would, and Message Evaluator already forbids both
    (`evaluator/sources.py`: persona context may establish a role, "never what
    that person thinks, wants or has said").

    Full names and long single tokens only. A four-character minimum on the
    parts keeps ordinary words out of the ban list - several surnames on this
    roster collide with English words at three characters, and a persona that
    cannot use the word "long" is worse than one that says a surname.
    """
    found = set()
    for contact in _contacts(account_id):
        full = _text(contact.get("full_name"))
        if not full:
            continue
        found.add(full)
        for part in full.replace("(", " ").replace(")", " ").split():
            if len(part) > 4:
                found.add(part)
    return sorted(found, key=len, reverse=True)


def prompt_block(persona: dict) -> str:
    """What the model is told about who it is playing.

    **The name is deliberately absent.** Everything here is role: title,
    department, seniority, influence, and the concerns Stakeholder Map recorded
    against that role. A model given the name writes the name, and then the
    transcript reads as a real employee's quoted position on HP - which is the
    one thing this feature must never produce.

    The concerns and objections are listed rather than left to be found in the
    payload. They are already in it, in full, with their citations - but a
    persona whose specific ammunition is named up front pushes back on what this
    account's evidence actually supports, instead of on whatever the model
    thinks a person with that title would say.
    """
    lines = ["You are playing THE %s." % (persona.get("title") or "").upper()]
    for key, label in (("department", "Department"),
                       ("seniority_band", "Seniority"),
                       ("influence_type", "Influence in the buying group")):
        if persona.get(key):
            lines.append("- %s: %s" % (label, persona[key]))
    if persona.get("decision_power"):
        lines.append("- What this role decides: %s" % persona["decision_power"])
    if persona.get("hp_play_focus"):
        lines.append("- Where HP is relevant to it: %s" % persona["hp_play_focus"])

    for point in (persona.get("pain_points") or [])[:4]:
        lines.append("- A concern recorded against this role: %s" % _text(point))

    for card in (persona.get("objections") or [])[:5]:
        lines.append("- An objection this role is expected to raise: %s"
                     % card["objection"])

    if persona.get("pain_points") or persona.get("objections"):
        lines.append(
            "These are yours to raise and the evidence for them is in the "
            "context below. When you raise one, find the line in the context "
            "that says it and cite that line's tag. Nothing written above "
            "carries a tag, so never cite anything from this section.")

    return "\n".join(lines)


def suggested_prompts(persona: dict) -> list:
    """Openers for a rehearsal, built from this persona's own evidence.

    Deterministic. The advisor's starters are phrased for a seller asking about
    an account; these are phrased for a seller about to be pushed back on, and
    each one points at something the persona can actually answer from.
    """
    role = persona.get("title") or "this role"
    found = [{
        "id": "open",
        "title": "Make your opening",
        "prompt_text": "I have 30 seconds with you. Here is my pitch: HP can "
                       "modernise your device estate. Push back on me.",
    }]

    for index, card in enumerate((persona.get("objections") or [])[:2]):
        found.append({
            "id": "objection_%d" % index,
            "title": "Handle: %s" % (card["area"] or "an objection"),
            "prompt_text": "Let's talk about %s. Tell me why HP is not the "
                           "obvious answer." % (card["area"] or "this area"),
        })

    if persona.get("pain_points"):
        found.append({
            "id": "pain",
            "title": "Probe the concern",
            "prompt_text": "What is actually making your job harder right now?",
        })

    found.append({
        "id": "why_you",
        "title": "Test the fit",
        "prompt_text": "Why should %s care about this rather than someone "
                       "else here?" % role,
    })
    return found
