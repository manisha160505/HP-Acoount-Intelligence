"""The rest of Sahaj's 27 Sep feedback on the Advantest sample (DEC-060):
Intent & Demand's business-unit summary, Content Studio's formats and topics,
Message Evaluator's three formats, and Strategy Chat's answer structure. The
Live Signals T0-T3 tiers are pinned in test_signal_batching.py.

Run: python -m pytest tests/test_sahaj_feedback_remaining.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.evaluator import formats as ef
from app.services.extractors import content_studio as cstudio, intent_demand_signals as ids
from app.services.hp import intent_topic_map as tm
from app.services.strategy import chat


def _topic(name, score, category, included=True):
    return {"topic_name": name, "composite_score": score, "hp_category": category,
            "included": included}


def _cat(name, score, stage="Awareness"):
    return {"category": name, "primary": {"score": score, "stage": stage}}


class TestTheBusinessUnitSummary:
    """ "for the 173 accounts for which Bombora intent is available, let's lead
    with those and add a broad summary at the start that mentions intent around
    HP's key business units ... For the accounts post the 173 accounts, please
    use the Predictleads data for capturing intent." """

    PC, WS = tm.CAT_PC, tm.CAT_WORKSTATION

    def test_all_five_units_are_listed(self):
        out = ids._bu_summary([], [])
        assert len(out["units"]) == 5
        assert {u["category"] for u in out["units"]} == {c["category"] for c in tm.HP_CATEGORIES}

    def test_bombora_leads_where_the_account_has_topics(self):
        topics = [_topic("Desktop: End User Digital", 73, self.PC),
                  _topic("Personal Computer: 2-In-1 Pcs", 72, self.PC),
                  _topic("Hpc Investment", 89, self.WS)]
        out = ids._bu_summary(topics, [_cat(self.PC, 5), _cat(self.WS, 38)])
        assert out["lead_source"] == "Bombora"
        first = out["units"][0]
        assert first["category"] == self.WS and first["bombora_max"] == 89
        pc = next(u for u in out["units"] if u["category"] == self.PC)
        # The PC 5/100 case: the Bombora research is shown beside the file's
        # score, neither replacing the other.
        assert pc["bombora_topic_count"] == 2 and pc["bombora_max"] == 73
        assert pc["category_file_score"] == 5
        assert pc["bombora_top_topics"][0] == {"topic": "Desktop: End User Digital",
                                               "score": 73}

    def test_the_category_file_leads_without_bombora(self):
        out = ids._bu_summary([], [_cat(self.PC, 5), _cat(self.WS, 38)])
        assert out["lead_source"] == "PredictLeads"
        assert out["units"][0]["category"] == self.WS

    def test_excluded_topics_do_not_count(self):
        out = ids._bu_summary([_topic("noise", 99, self.PC, included=False)], [])
        pc = next(u for u in out["units"] if u["category"] == self.PC)
        assert pc["bombora_topic_count"] == 0 and out["lead_source"] == "PredictLeads"


class TestContentStudioFormatsAndTopics:
    def test_three_formats_in_the_client_s_order(self):
        assert cstudio.OFFERED_CONTENT_TYPES == ("email", "linkedin_message", "one_pager")
        for key in cstudio.OFFERED_CONTENT_TYPES:
            assert key in cstudio.CONTENT_TYPE_CONTRACTS

    def test_a_linkedin_message_is_a_message_not_a_post(self):
        c = cstudio.CONTENT_TYPE_CONTRACTS["linkedin_message"]
        assert c["title"] == "LinkedIn Message"
        assert "headline" not in c["required"] and not c.get("public")
        assert c["words"][1] <= 80

    def test_the_topics_are_the_five_business_units(self):
        assert len(cstudio.HP_BU_TOPICS) == 5
        assert "HP Multi Jet Fusion (3D)" in cstudio.HP_BU_TOPICS

    def test_older_contracts_still_resolve_for_saved_assets(self):
        for key in ("linkedin", "exec_brief", "follow_up", "branded_emailer", "landing_page"):
            assert key in cstudio.CONTENT_TYPE_CONTRACTS


class TestMessageEvaluatorFormats:
    def test_three_formats_are_offered(self):
        assert [f["id"] for f in ef.catalogue()] == ["email", "linkedin_message", "one_pager"]

    def test_the_one_pager_is_checked_like_one(self):
        spec = ef.FORMATS["one_pager"]
        assert spec["label"] == "One-Pager Exec Brief"
        assert spec["rewrite"]["sections"] == (4, 4) and spec["wants_headings"]

    def test_older_formats_still_normalise(self):
        assert ef.normalize_format("Social Post") == "social_post"


class TestStrategyChatStructure:
    def test_the_prompt_asks_for_the_answer_first(self):
        system = chat.ANSWER_SYSTEM
        assert system.index("ANSWER:") < system.index("FACTS:") < system.index("RECOMMENDED NEXT STEPS:")
        assert chat.PROMPT_VERSION >= 2

    def test_a_facts_section_after_a_long_answer_still_needs_citations(self):
        answer = ("ANSWER:\n" + "Workstations have the strongest case. " * 20
                  + "\nFACTS:\n1. The account runs ANSYS.\n")
        assert chat._asserts_facts(answer)

    def test_a_plain_refusal_is_not_a_fact(self):
        assert not chat._asserts_facts("ANSWER: The platform does not hold that.")


from app.services.extractors import tech_landscape as tl

STACK_MATRIX = {"It Security": ["Aruba ClearPass"],
          "Bi And Analytics": ["Tableau", "Apache Spark MLlib"],
          "Devops And Development": ["Apache Spark MLlib", "Git"]}
STACK_NAMES = ["Aruba ClearPass", "Tableau", "Apache Spark MLlib", "Git", "Mystery Tool"]
STACK_CARDS = [{"category_name": "Workstations & High-Performance Compute", "vendors": [
            {"vendor_name": "AI / ML frameworks", "detected_as": ["Apache Spark MLlib"],
             "risk_level": "High risk",
             "hp_play": {"product": "Z by HP Workstations", "play_text": "Z for ML."}}]},
         {"category_name": "Client OS", "vendors": [
            {"vendor_name": "Microsoft", "detected_as": ["Windows 10"], "hp_play": None}]}]


class TestTheTechnographicStackView:
    """The Caterpillar-style layout: every technology a card, in families,
    with the HP play the map found for it - and nothing scored."""

    def view(self):
        return tl.stack_view(STACK_MATRIX, STACK_NAMES, {"git": "hp_category_intent"}, STACK_CARDS)

    def test_every_technology_is_a_card(self):
        assert self.view()["total"] == 5

    def test_a_multi_column_technology_takes_the_first_family(self):
        spark = next(t for t in self.view()["technologies"] if t["name"] == "Apache Spark MLlib")
        assert spark["family"] == "Engineering & Development"
        assert set(spark["export_categories"]) == {"Bi And Analytics", "Devops And Development"}

    def test_uncategorised_is_other(self):
        tool = next(t for t in self.view()["technologies"] if t["name"] == "Mystery Tool")
        assert tool["family"] == "Other" and tool["hp"] is None

    def test_the_hp_play_and_approved_risk_label_are_copied(self):
        spark = next(t for t in self.view()["technologies"] if t["name"] == "Apache Spark MLlib")
        assert spark["hp"] == {"hp_play": "Z by HP Workstations",
                               "hp_category": "Workstations & High-Performance Compute",
                               "risk_level": "High risk", "reason": "Z for ML.",
                               "vendor": "AI / ML frameworks"}
        assert "confidence" not in str(spark)

    def test_the_opportunities_roll_up(self):
        opps = self.view()["opportunities"]
        assert [(o["hp_play"], o["technology_count"]) for o in opps] == [("Z by HP Workstations", 1)]

    def test_sources_are_labelled(self):
        v = self.view()
        git = next(t for t in v["technologies"] if t["name"] == "Git")
        assert git["source"] == "Intent file"
        assert {s["label"] for s in v["sources"]} == {"Technographics", "Intent file"}


class TestNoTrendWords:
    """ "please drop the tags increasing or stable, etc. as we are not showing
    intent trend" - including in the model-written So What."""

    def test_the_so_what_is_never_given_a_trend_or_volume(self, monkeypatch):
        sent = []
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion",
                            lambda _system, user: sent.append(user) or {})
        ids._so_what("Acme", [{"category": "PC", "hp_play": "HP Elite & Pro PCs",
                               "primary": {"score": 40, "stage": "Awareness",
                                           "trend_label": "Increasing",
                                           "research_volume": "High"}}])
        assert sent and "Increasing" not in sent[0] and "High" not in sent[0]
        assert "trend" not in sent[0] and "research_volume" not in sent[0]

    def test_the_prompt_forbids_trend_words(self):
        assert "increasing, decreasing" in ids.SO_WHAT_SYSTEM
        assert "its trend" not in ids.SO_WHAT_SYSTEM


class TestContentStudioFindsTheBuyingCommittee:
    """Sahaj's screenshot: "Unknown persona_id 'role_chief_technology_officer_cto'
    for this account". Suggesting angles and generating share one lookup, so the
    buying-committee roles must resolve there or neither step works for them."""

    def test_a_client_role_id_resolves(self, monkeypatch):
        role = {"target_persona": "Chief Technology Officer (CTO)", "department": "IT",
                "buying_committee_angle": "", "contact_name": "", "actual_job_title": "",
                "work_email": "", "phone_number": "", "linkedin_url": "",
                "contact_status": "", "source": "", "matched_alias": "", "is_filled": False}
        monkeypatch.setattr(cstudio.personas, "read_roles", lambda _aid: [role])
        monkeypatch.setattr(cstudio, "_derive_named_personas", lambda _db, _aid: [])
        found = cstudio._persona_by_id(None, "acct", [], "role_chief_technology_officer_cto")
        assert found is not None and found["id"] == "role_chief_technology_officer_cto"


class TestTheBusinessUnitReads:
    """Sahaj, 28 Sep: "on top we can show the summary from the bombora data
    itself, llm can generate in cards". The model writes one line per unit; the
    numbers on the card stay Python's."""

    def test_a_read_carrying_a_figure_is_dropped(self, monkeypatch):
        """Rule 4. The card already prints the count and the maximum, so a
        number inside the prose is either a repetition or an invention."""
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "The research leans towards print and desktop conversations here.",
            "units": [{"category": ids.tm.CAT_PC,
                       "read": "Four topics point to a desktop refresh conversation "
                               "worth opening on with the workplace team."}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC, "hp_play": "HP Elite",
                                      "bombora_top_topics": [{"topic": "2-in-1 pcs", "score": 72}]}])
        assert out["reads"] == {}

    def test_the_models_own_spelling_of_a_topic_still_counts(self, monkeypatch):
        """The topic is "personal computer: 2-in-1 pcs" and the model writes
        "2-in-1 PCs". Matching whole names left the digit behind and dropped
        the read; the token is what is checked."""
        text = ("The interest in end user digital experiences, 2-in-1 PCs and "
                "desktop apps may indicate an opening to discuss how the fleet "
                "supports modern work.")
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "", "units": [{"category": ids.tm.CAT_PC, "read": text}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC,
                                      "hp_play": "HP Elite & Pro PCs",
                                      "bombora_top_topics": [
                                          {"topic": "personal computer: 2-in-1 pcs", "score": 72},
                                          {"topic": "desktop: desktop apps", "score": 64}]}])
        assert out["reads"][ids.tm.CAT_PC] == text

    def test_a_percentage_is_still_a_figure(self, monkeypatch):
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "", "units": [{"category": ids.tm.CAT_PC,
                                       "read": "Interest is up 20% this quarter, which "
                                               "suggests a fleet conversation is worth "
                                               "opening with the workplace team."}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC, "hp_play": "HP Elite",
                                      "bombora_top_topics": [{"topic": "2-in-1 pcs", "score": 72}]}])
        assert out["reads"] == {}

    def test_a_name_with_a_digit_in_it_is_not_a_figure(self, monkeypatch):
        """The unit is called 3D and one topic is "2-in-1 pcs". The first cut
        of the no-figures rule dropped every read that named either."""
        text = ("For 3D, no researched topic maps to this unit, so the opening "
                "conversation would have to start from somewhere else entirely.")
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "", "units": [{"category": ids.tm.CAT_3D, "read": text}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_3D,
                                      "hp_play": "HP Multi Jet Fusion (3D)",
                                      "bombora_top_topics": [{"topic": "2-in-1 pcs", "score": 72}]}])
        assert out["reads"][ids.tm.CAT_3D] == text

    def test_a_clean_read_is_kept(self, monkeypatch):
        text = ("Research on two-in-one desktops suggests a fleet conversation "
                "could be worth opening on with the workplace team soon.")
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "", "units": [{"category": ids.tm.CAT_PC, "read": text}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC, "hp_play": "HP Elite",
                                      "bombora_top_topics": [{"topic": "2-in-1 pcs", "score": 72}]}])
        assert out["reads"][ids.tm.CAT_PC] == text

    def test_a_read_outside_the_word_band_is_dropped(self, monkeypatch):
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "", "units": [{"category": ids.tm.CAT_PC, "read": "Worth a look."}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC, "hp_play": "HP Elite",
                                      "bombora_top_topics": [{"topic": "2-in-1 pcs", "score": 72}]}])
        assert out["reads"] == {}

    def test_an_account_with_no_researched_topic_is_never_sent(self, monkeypatch):
        """No topics, nothing to read - and no call to pay for."""
        called = []
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion",
                            lambda *_a, **_k: called.append(1))
        assert ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC, "hp_play": "HP Elite",
                                       "bombora_top_topics": []}]) == {}
        assert called == []

    def test_a_model_failure_costs_prose_and_nothing_else(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("upstream is down")
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", boom)
        assert ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC, "hp_play": "HP Elite",
                                       "bombora_top_topics": [{"topic": "x", "score": 1}]}]) == {}
