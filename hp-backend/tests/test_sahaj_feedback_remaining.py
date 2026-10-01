"""The rest of Sahaj's 27 Sep feedback on the Advantest sample (DEC-060):
Intent & Demand's business-unit summary, Content Studio's formats and topics,
Message Evaluator's three formats, and Strategy Chat's answer structure. The
Live Signals T0-T3 tiers are pinned in test_signal_batching.py.

Run: python -m pytest tests/test_sahaj_feedback_remaining.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from app.services.evaluator import formats as ef
from app.services.extractors import content_studio as cstudio, intent_demand_signals as ids
from app.services.hp import content_gates, intent_topic_map as tm
from app.services.strategy import chat


def _topic(name, score, category, included=True, theme=tm.THEME_DEVICES):
    """A scored Bombora topic. `theme` is what groups it into a card now; the
    HP category is kept for the tests that still assert on the category view."""
    return {"topic_name": name, "composite_score": score, "hp_category": category,
            "theme": theme, "included": included}


def _cat(name, score, stage="Awareness"):
    return {"category": name, "primary": {"score": score, "stage": stage}}


class TestTheBusinessUnitSummary:
    """ "for the 173 accounts for which Bombora intent is available, let's lead
    with those and add a broad summary at the start that mentions intent around
    HP's key business units ... For the accounts post the 173 accounts, please
    use the Predictleads data for capturing intent." """

    PC, WS = tm.CAT_PC, tm.CAT_WORKSTATION

    def test_all_five_units_are_listed_without_bombora(self):
        """The PredictLeads path is unchanged: no Bombora, so HP's own five."""
        out = ids._bu_summary([], [])
        assert len(out["units"]) == 5
        assert {u["category"] for u in out["units"]} == {c["category"] for c in tm.HP_CATEGORIES}

    def test_bombora_leads_and_groups_by_theme(self):
        """The units on a Bombora account are the account's own research
        themes (Sahaj, 30 Sep). The topics below all map to Devices &
        Endpoints, so that is the card they make - one card, three topics,
        rather than three of HP's five units."""
        topics = [_topic("Desktop: End User Digital", 73, self.PC),
                  _topic("Personal Computer: 2-In-1 Pcs", 72, self.PC),
                  _topic("Hpc Investment", 89, self.WS)]
        out = ids._bu_summary(topics, [_cat(self.PC, 5), _cat(self.WS, 38)])
        assert out["lead_source"] == "Bombora"
        assert out["unit_kind"] == "theme"
        assert {u["category"] for u in out["units"]} <= set(tm.THEMES)
        strongest = out["units"][0]
        assert strongest["bombora_max"] == 89
        assert strongest["bombora_top_topics"][0] == {"topic": "Hpc Investment",
                                                      "score": 89}
        # A theme is not an HP line, so it carries no play and no file score.
        assert all(u["hp_play"] is None for u in out["units"])
        assert all(u["category_file_score"] is None for u in out["units"])

    def test_the_category_file_leads_without_bombora(self):
        out = ids._bu_summary([], [_cat(self.PC, 5), _cat(self.WS, 38)])
        assert out["lead_source"] == "PredictLeads"
        assert out["units"][0]["category"] == self.WS

    def test_excluded_topics_do_not_count(self):
        """An excluded topic is not research, so it makes no theme and does not
        turn the account into a Bombora one."""
        out = ids._bu_summary([_topic("noise", 99, self.PC, included=False)], [])
        assert out["lead_source"] == "PredictLeads"
        assert out["unit_kind"] == "hp_category"
        assert all(u["bombora_topic_count"] == 0 for u in out["units"])


class TestContentStudioFormatsAndTopics:
    def test_three_formats_in_the_client_s_order(self):
        assert cstudio.OFFERED_CONTENT_TYPES == ("email", "linkedin_message", "one_pager")
        for key in cstudio.OFFERED_CONTENT_TYPES:
            assert key in cstudio.CONTENT_TYPE_CONTRACTS

    def test_a_linkedin_message_is_a_message_not_a_post(self):
        c = cstudio.CONTENT_TYPE_CONTRACTS["linkedin_message"]
        assert c["title"] == "LinkedIn Message"
        assert "headline" not in c["required"] and not c.get("public")
        # Short, and the contract no longer says how short. The 30 Sep build
        # specification sets 60-110 words and makes a budget miss "regenerate
        # once"; carried here as well it would also be a hard fault, and a
        # 55-word message would be withheld from the seller instead of
        # rewritten. `content_gates.WORD_BUDGETS` is the one owner.
        assert "words" not in c
        assert content_gates.WORD_BUDGETS["linkedin_message"] == (60, 110)

    def test_the_topics_are_the_five_business_units(self):
        assert len(cstudio.HP_BU_TOPICS) == 5
        assert "HP Multi Jet Fusion (3D)" in cstudio.HP_BU_TOPICS

    def test_the_retired_content_types_keep_their_names_and_nothing_else(self):
        """Spec 1.2: "Do not leave the code path in \'just in case\'."

        These five kept full contracts so a stored asset would still render.
        That reason did not survive checking - an asset stores its own
        `plain_text` and `rendered_html` at generation time, so displaying one
        never reads a contract. What the contracts bought was the ability to
        generate against a rubric no seller can choose.
        """
        for key in ("linkedin", "exec_brief", "follow_up", "branded_emailer",
                    "landing_page"):
            assert key not in cstudio.CONTENT_TYPE_CONTRACTS
            assert key in cstudio.RETIRED_CONTENT_TYPES
        assert list(cstudio.CONTENT_TYPE_CONTRACTS) == list(cstudio.OFFERED_CONTENT_TYPES)

    def test_asking_for_a_retired_type_says_so(self):
        """A seller replaying an old link gets "retired", not "unknown"."""
        with pytest.raises(ValueError, match="no longer generated"):
            cstudio._build_generation_context(
                None, "acct", "cfo", "branded_emailer", "a topic", "")


class TestMessageEvaluatorFormats:
    def test_three_formats_are_offered(self):
        assert [f["id"] for f in ef.catalogue()] == ["email", "linkedin_message", "one_pager"]

    def test_the_one_pager_is_checked_like_one(self):
        spec = ef.FORMATS["one_pager"]
        assert spec["label"] == "One-Pager Exec Brief"
        assert spec["rewrite"]["sections"] == (4, 4) and spec["wants_headings"]

    def test_the_retired_formats_keep_their_names_and_nothing_else(self):
        """Spec 1.2 names these five and says to remove the code path.

        They were kept so an evaluation stored under one would still read. An
        evaluation stores its own `format_label`, so re-reading one never
        consults the table - what the contracts actually bought was the
        ability to score against a rubric no seller can choose.
        """
        for key in ("social_post", "website_copy", "tech_blog",
                    "message_planks", "campaign_idea"):
            assert key not in ef.FORMATS
            assert key in ef.RETIRED_FORMATS
        assert sorted(ef.FORMATS) == sorted(ef.OFFERED_FORMATS)

    def test_a_retired_format_says_retired_rather_than_unknown(self):
        with pytest.raises(ef.FormatError, match="was retired"):
            ef.normalize_format("Social Post")
        with pytest.raises(ef.FormatError, match="unknown format"):
            ef.normalize_format("not-a-format")

    def test_but_a_new_evaluation_may_only_use_the_three(self):
        """`OFFERED_FORMATS` gated the dropdown and nothing else, so
        `POST .../evaluate` with "format": "tech_blog" was scored - against a
        rubric for a format the seller cannot pick and Section 2.3 has no row
        for. The narrow check lives at the entry point; the wide reader stays
        where reading happens."""
        for key in ef.OFFERED_FORMATS:
            assert ef.normalize_offered_format(key) == key
        for key in ("social_post", "website_copy", "tech_blog", "message_planks"):
            if key not in ef.FORMATS:
                continue
            with pytest.raises(ef.FormatError):
                ef.normalize_offered_format(key)

    def test_the_evaluator_criteria_are_the_specification_s(self):
        """Spec Section 4.5 "replaces FORMAT_CRITERIA entirely" for the three."""
        assert "greeting boilerplate" in ef.FORMATS["email"]["criteria"]
        assert "could be sent to anyone" in ef.FORMATS["linkedin_message"]["criteria"]
        assert "standalone leave-behind" in ef.FORMATS["one_pager"]["criteria"]


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
    """Suggesting angles and generating share one persona lookup, so a persona
    the picker offers must resolve there or neither step works for it.

    The lookup narrowed on 30 Sep: the client's `company_personas` carries
    thirty-two target roles per account and the build specification locks the
    programme to eight of them. A role outside the eight no longer resolves,
    and that is the scope lock working rather than the bug this class was
    written for."""

    def _roles(self, *titles):
        return [{"target_persona": t, "department": "IT",
                 "buying_committee_angle": "", "contact_name": "",
                 "actual_job_title": "", "work_email": "", "phone_number": "",
                 "linkedin_url": "", "contact_status": "", "source": "",
                 "matched_alias": "", "is_filled": False} for t in titles]

    def test_a_persona_in_scope_resolves(self, monkeypatch):
        monkeypatch.setattr(cstudio.personas, "read_roles",
                            lambda _aid: self._roles("IT Security Manager"))
        monkeypatch.setattr(cstudio, "_derive_named_personas", lambda _db, _aid: [])
        found = cstudio._persona_by_id(None, "acct", [], "it-security-manager")
        assert found is not None
        assert found["id"] == "it-security-manager"
        assert found["kind"] == "client_role"

    def test_a_role_outside_the_eight_is_never_offered(self, monkeypatch):
        """The CTO is one of the twenty-four roles the file carries that this
        programme does not write to. It is dropped - and the eight are still
        offered, because spec 1.4 says "treat all eight as client target
        roles" and the file decides only FILLED or UNFILLED."""
        from app.services.hp import buyer_personas as bp
        monkeypatch.setattr(cstudio.personas, "read_roles",
                            lambda _aid: self._roles("Chief Technology Officer (CTO)"))
        out = cstudio._derive_client_personas("acct")
        assert [p["id"] for p in out] == list(bp.PERSONA_IDS)
        assert all(not p["is_filled"] for p in out)

    def test_an_account_with_no_target_role_file_still_has_eight(self, monkeypatch):
        """The bug this replaced: the eight were gated on the file having a
        matching row, so an account without it offered none at all."""
        from app.services.hp import buyer_personas as bp
        monkeypatch.setattr(cstudio.personas, "read_roles", lambda _aid: [])
        out = cstudio._derive_client_personas("acct")
        assert [p["id"] for p in out] == list(bp.PERSONA_IDS)
        assert all(not p["is_filled"] and p["full_name"] is None for p in out)


class TestTheBusinessUnitReads:
    """Sahaj, 28 Sep: "on top we can show the summary from the bombora data
    itself, llm can generate in cards". The model writes one line per unit; the
    numbers on the card stay Python's."""

    def test_a_read_carrying_a_figure_is_dropped(self, monkeypatch):
        """Rule 4. The card already prints the count and the maximum, so a
        number inside the prose is either a repetition or an invention."""
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "The research leans towards print and desktop conversations here.",
            "themes": [{"theme": ids.tm.CAT_PC,
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
            "overview": "", "themes": [{"theme": ids.tm.CAT_PC, "read": text}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC,
                                      "hp_play": "HP Elite & Pro PCs",
                                      "bombora_top_topics": [
                                          {"topic": "personal computer: 2-in-1 pcs", "score": 72},
                                          {"topic": "desktop: desktop apps", "score": 64}]}])
        assert out["reads"][ids.tm.CAT_PC] == text

    def test_a_percentage_is_still_a_figure(self, monkeypatch):
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "", "themes": [{"theme": ids.tm.CAT_PC,
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
            "overview": "", "themes": [{"theme": ids.tm.CAT_3D, "read": text}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_3D,
                                      "hp_play": None,
                                      "bombora_top_topics": [{"topic": "2-in-1 pcs", "score": 72}]}])
        assert out["reads"][ids.tm.CAT_3D] == text

    def test_a_clean_read_is_kept(self, monkeypatch):
        text = ("Research on two-in-one desktops suggests a fleet conversation "
                "could be worth opening on with the workplace team soon.")
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "", "themes": [{"theme": ids.tm.CAT_PC, "read": text}]})
        out = ids._bu_reads("A Co", [{"category": ids.tm.CAT_PC, "hp_play": "HP Elite",
                                      "bombora_top_topics": [{"topic": "2-in-1 pcs", "score": 72}]}])
        assert out["reads"][ids.tm.CAT_PC] == text

    def test_a_read_outside_the_word_band_is_dropped(self, monkeypatch):
        monkeypatch.setattr(ids, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "overview": "", "themes": [{"theme": ids.tm.CAT_PC, "read": "Worth a look."}]})
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


# ---------------------------------------------------------------------------
# Intent & Demand: the account's own themes, not HP's five units
#
# Sahaj, 30 Sep. Three changes, all on a Bombora account:
#   * the cards and the chart group by the RESEARCH THEME the dictionary
#     assigns, not by HP business unit - Advantest researches across eight
#     themes and folding them into five discarded most of the export;
#   * "Other / Low Relevance" is not one of them: it is the residue, and it has
#     its own section;
#   * the HP Category Intent file's scores leave "So what for HP" entirely -
#     that is the PredictLeads answer to the same question, and an account with
#     Bombora leads with Bombora.
# ---------------------------------------------------------------------------

# `ids` and `tm` are imported at the top of this file; `itm` is the same module
# as `tm`, named here because these tests read as being about the dictionary.
itm = tm


def _mapped_topic(name, score):
    """A topic carrying whatever theme the dictionary actually assigns it.

    Named apart from the `_topic` helper at the top of this file, which takes
    an HP category: these tests are about the theme the dictionary chooses, so
    nothing here may name one.
    """
    return {"topic_name": name, "composite_score": score, "included": True,
            "hiring_linked": False, **itm.map_topic(name)}


BOMBORA_TOPICS = [
    _mapped_topic("security: endpoint protection", 97),
    _mapped_topic("cloud: kubernetes", 93),
    _mapped_topic("collaboration: video conferencing", 90),
    _mapped_topic("print: managed print services", 84),
    _mapped_topic("general: unmapped oddity", 70),
]
FILE_CATEGORIES = [{"category": c["category"],
                    "primary": {"score": 35, "stage": "Awareness",
                                "has_signal": False}}
                   for c in itm.HP_CATEGORIES]
CATEGORY_FILE = {"status": "matched", "categories": {
    "3D": {"score": 35, "stage": "Awareness", "has_signal": False},
    "Print": {"score": 13, "stage": "No Signal", "has_signal": False}}}


class TestTheUnitsAreTheAccountsOwnThemes:
    def test_a_bombora_account_is_grouped_by_theme(self):
        bu = ids._bu_summary(BOMBORA_TOPICS, FILE_CATEGORIES)
        assert bu["lead_source"] == "Bombora"
        assert bu["unit_kind"] == "theme"
        assert bu["source_label"] == "Bombora"
        names = [u["category"] for u in bu["units"]]
        assert names, "a Bombora account must produce theme units"
        assert set(names) <= set(itm.THEMES)
        assert not set(names) & {c["category"] for c in itm.HP_CATEGORIES
                                 if c["category"] != "Print"}

    def test_the_residue_is_not_a_theme_card(self):
        """"Other / Low Relevance" is what the dictionary did not place. It has
        its own section further down and is not one of the cards."""
        bu = ids._bu_summary(BOMBORA_TOPICS, FILE_CATEGORIES)
        assert itm.THEME_OTHER not in [u["category"] for u in bu["units"]]

    def test_a_theme_never_carries_an_hp_play(self):
        """The dictionary gives its context themes no HP category on purpose.
        Inventing one here would put an HP play behind "E-commerce &
        Logistics"."""
        bu = ids._bu_summary(BOMBORA_TOPICS, FILE_CATEGORIES)
        assert all(u["hp_play"] is None for u in bu["units"])

    def test_an_empty_theme_gets_no_card(self):
        bu = ids._bu_summary(BOMBORA_TOPICS, FILE_CATEGORIES)
        assert all(u["bombora_topic_count"] > 0 for u in bu["units"])

    def test_the_strongest_theme_leads(self):
        bu = ids._bu_summary(BOMBORA_TOPICS, FILE_CATEGORIES)
        maxes = [u["bombora_max"] for u in bu["units"]]
        assert maxes == sorted(maxes, reverse=True)

    def test_an_account_without_bombora_still_gets_hps_five_units(self):
        """The other half of the client's rule: no Bombora, so the category
        file leads and the units are HP's own."""
        bu = ids._bu_summary([], FILE_CATEGORIES)
        assert bu["lead_source"] == "PredictLeads"
        assert bu["unit_kind"] == "hp_category"
        assert {u["category"] for u in bu["units"]} == {
            c["category"] for c in itm.HP_CATEGORIES}


class TestOneSourceLeadsTheSoWhat:
    def test_a_bombora_account_does_not_print_the_category_file_scores(self):
        """The line the client pointed at: "HP Category Intent file scores: 3D
        35/100 (Awareness); Print 13/100 (No Signal)..." on an account whose
        intent comes from Bombora."""
        out = ids._summarise(BOMBORA_TOPICS, CATEGORY_FILE, [])
        assert not any("HP Category Intent file scores" in line
                       for line in out["so_what"])
        assert not any("category file" in line.lower() for line in out["so_what"])

    def test_an_account_without_bombora_still_shows_them(self):
        out = ids._summarise([], CATEGORY_FILE, [])
        assert any("HP Category Intent file scores" in line
                   for line in out["so_what"])
