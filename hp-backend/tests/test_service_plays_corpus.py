"""The service half of the rulebook reaching the features that read prose.

162 rules load; 18 of them are Part A hardware and reach the Technographic Map.
The other 144 - every care, deployment, lifecycle, Poly, print, scan and ink
rule, including all 49 the client added in the FINAL revision - were written
into the Opportunity Map's `service_plays` and then read by nothing. The
retrieval corpus indexed `opportunity_plays` beside them and skipped them, so
Content Messaging, Strategy Chat and the Message Evaluator could only ever
speak about HP hardware, and nothing failed to say so.

Run: python -m pytest tests/test_service_plays_corpus.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.retrieval import corpus


class Builder:
    """Stands in for the citation builder, recording what it was asked to cite."""

    def __init__(self):
        self.cited = []

    def line(self, text, field=None, record_id=None, dataset=None,
             quote=None, source_url=None):
        self.cited.append({"text": text, "field": field, "dataset": dataset})
        return "%s [id]" % text


def play(**over):
    base = {
        "play_key": "wxp-07",
        "rule_label": "WXP 07",
        "opportunity_type": "Workforce experience",
        "title": "HP Workforce Experience Platform (WXP)",
        "allowed_facts": ["Mention only the integration that matches the "
                          "account evidence."],
        "prohibitions": ["Do not present existing use as buying intent."],
        "account_evidence": [{"text": "Microsoft Power BI",
                              "dataset": "technographics",
                              "field": "Full Tech Stack"}],
    }
    base.update(over)
    return base


class TestAServicePlayReachesTheCorpus:
    def test_its_approved_facts_are_indexed_as_citable_lines(self):
        """A rule's `allowed_facts` are HP's own approved sentences. Summarising
        them would put an unapproved sentence where an approved one belongs, so
        each is indexed whole and carries its own identifier."""
        b = Builder()
        out = corpus._fill_service_plays(b, {"service_plays": [play()]})
        facts = [c for c in b.cited if c["field"] == "allowed_facts"]
        assert len(facts) == 1
        assert facts[0]["text"].startswith("Mention only the integration")
        assert any("HP approved fact" in line for line in out)

    def test_a_prohibition_travels_with_the_offering(self):
        """A pillar shown the offering and not its prohibition can write the one
        sentence the rulebook rules out."""
        b = Builder()
        corpus._fill_service_plays(b, {"service_plays": [play()]})
        bans = [c for c in b.cited if c["field"] == "prohibitions"]
        assert len(bans) == 1
        assert "buying intent" in bans[0]["text"]

    def test_account_evidence_keeps_its_own_dataset(self):
        """A play restates a technographics cell, it does not originate it. The
        citation has to name the real source or a seller asked "where did this
        come from" is pointed at the play it was assembled in."""
        b = Builder()
        corpus._fill_service_plays(b, {"service_plays": [play()]})
        cells = [c for c in b.cited if c["dataset"] == "technographics"]
        assert len(cells) == 1
        assert cells[0]["field"] == "Full Tech Stack"

    def test_the_opportunity_type_labels_the_play(self):
        b = Builder()
        out = corpus._fill_service_plays(b, {"service_plays": [play()]})
        assert "Workforce experience" in out[0]

    def test_a_play_with_no_title_is_skipped_rather_than_half_rendered(self):
        b = Builder()
        assert corpus._fill_service_plays(b, {"service_plays": [play(title="")]}) == []

    def test_no_service_plays_renders_nothing(self):
        assert corpus._fill_service_plays(Builder(), {}) == []
