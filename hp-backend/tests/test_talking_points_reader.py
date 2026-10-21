"""A talking point joined by contact_id belongs to the person it was written for.

Each stored entry records the full name it was written for. A contact id can
come to name someone else after a contacts reload, so every reader - the
dashboard, Strategy Chat personas, Message Evaluator and the Strategy Chat
corpus - ignores an entry whose recorded name is not the contact's (21 Oct).

Run: python -m pytest tests/test_talking_points_reader.py -v
"""

import pytest

from app.services import talking_points
from app.services.retrieval import corpus

POINTS = {"c-1": {"full_name": "Adam Neal", "how_to_open": "Open on the refresh",
                  "pain_points": ["Ageing fleet"]},
          "c-2": {"how_to_open": "No name recorded"}}


@pytest.mark.parametrize("contact_id,name,expected", [
    ("c-1", "Adam Neal", POINTS["c-1"]),
    ("c-1", "  adam   NEAL ", POINTS["c-1"]),
    ("c-1", "Budi Santoso", {}),
    ("c-1", "", {}),
    ("c-2", "Anyone", POINTS["c-2"]),
    ("c-9", "Adam Neal", {}),
])
def test_for_contact(contact_id, name, expected):
    assert talking_points.for_contact(POINTS, contact_id, name) == expected


@pytest.mark.parametrize("bad", [None, [], "x", {"c-1": "not a dict"}])
def test_a_malformed_store_is_no_talking_points(bad):
    assert talking_points.for_contact(bad, "c-1", "Adam Neal") == {}


def test_the_chat_corpus_does_not_attach_another_persons_points(monkeypatch):
    widgets = {
        "stakeholder_contacts_grid": {"contacts": [
            {"contact_id": "c-1", "full_name": "Budi Santoso", "title": "CIO"}]},
        "stakeholder_influence_map": {},
        "stakeholder_talking_points": {"talking_points": POINTS},
    }
    monkeypatch.setattr(corpus, "_widget", lambda _db, _a, key: widgets.get(key, {}))
    docs = corpus._strategy_people_documents(None, "acct", 0, "Astra")
    text = " ".join(str(line) for d in docs for line in d.lines)
    assert "Budi Santoso" in text
    assert "Open on the refresh" not in text and "Ageing fleet" not in text

    widgets["stakeholder_contacts_grid"]["contacts"][0]["full_name"] = "Adam Neal"
    docs = corpus._strategy_people_documents(None, "acct", 0, "Astra")
    text = " ".join(str(line) for d in docs for line in d.lines)
    assert "Open on the refresh" in text and "Ageing fleet" in text
