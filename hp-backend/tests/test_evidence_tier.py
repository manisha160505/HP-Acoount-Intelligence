"""Sections C and D: how strongly a recommendation may be worded.

A tier is not a score. The three scoring documents each define their own scale
for their own feature and those stand; a tier governs what the PROSE may claim
on top of the number. A card can be a confident Tech Landscape match and still
only be allowed to say "this creates a relevant conversation", because one
pipeline saw it.

Run: python -m pytest tests/test_evidence_tier.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import evidence_tier as et


def rows(*datasets):
    return [{"text": "x", "dataset": d} for d in datasets]


class TestTheThresholdSectionCSets:
    def test_two_independent_pipelines_make_an_opportunity(self):
        out = et.tier_for(rows("hp_category_intent", "technographics"))
        assert out["tier"] == et.OPPORTUNITY
        assert out["pipeline_count"] == 2

    def test_one_pipeline_is_a_conversation_starter(self):
        """"1 strong, directly relevant signal ... but without a second
        independent pipeline confirming the same opportunity.\""""
        out = et.tier_for(rows("technographics"))
        assert out["tier"] == et.CONVERSATION_STARTER
        # The client's 25 Sep ladder replaced v4's example phrasing: one
        # pipeline lets an offering "may be relevant", never "is relevant".
        assert "may be relevant" in out["permitted_language"]
        assert et.relevance_for(out["tier"]) == et.RELEVANCE_MAY

    def test_three_pipelines_are_still_an_opportunity(self):
        out = et.tier_for(rows("intent_score", "job_openings", "google_news"))
        assert out["tier"] == et.OPPORTUNITY
        assert out["pipeline_count"] == 3


class TestDuplicateCoverageCountsOnce:
    """Section B: "when the same underlying event appears in Google News RSS,
    Exa and/or a filing, treat it as one event ... do not count them as
    independent corroboration." Both news feeds map to one pipeline, so this
    falls out of the mapping rather than needing a second dedup pass."""

    def test_both_news_feeds_are_one_pipeline(self):
        out = et.tier_for(rows("google_news", "news_events"))
        assert out["pipelines"] == ["News"]
        assert out["tier"] == et.CONVERSATION_STARTER

    def test_the_three_intent_files_are_one_pipeline(self):
        out = et.tier_for(rows("intent_score", "intent_topics", "hp_category_intent"))
        assert out["pipeline_count"] == 1

    def test_many_rows_from_one_pipeline_do_not_corroborate_themselves(self):
        out = et.tier_for(rows(*(["technographics"] * 40)))
        assert out["tier"] == et.CONVERSATION_STARTER


class TestContextCannotLiftATier:
    """Firmographics and contacts describe the account. They corroborate an
    opportunity something else established - the document's own example leans
    on an employee band - but cannot establish one."""

    def test_firmographics_alone_is_context_only(self):
        out = et.tier_for(rows("firmographics", "company_hierarchy"))
        assert out["tier"] == et.CONTEXT_ONLY
        assert "Do not create an HP opportunity" in out["permitted_language"]

    def test_firmographics_plus_contacts_is_still_context_only(self):
        assert et.tier_for(rows("firmographics", "prospect_contacts"))["tier"] == et.CONTEXT_ONLY

    def test_but_they_still_count_alongside_a_real_signal(self):
        out = et.tier_for(rows("technographics", "firmographics"))
        assert out["tier"] == et.CONVERSATION_STARTER
        assert "Firmographics" in out["pipelines"]
        assert "Firmographics" not in out["corroborating_pipelines"]


class TestNothingAddressableIsContextHoweverMuchEvidence:
    def test_unmatched_evidence_cannot_become_an_opportunity(self):
        """"Evidence ... does not establish an HP-addressable opportunity" ->
        Context Only, whatever the pipeline count."""
        out = et.tier_for(rows("intent_score", "technographics", "job_openings"),
                          hp_addressable=False)
        assert out["tier"] == et.CONTEXT_ONLY
        assert "no HP offering matches" in out["basis"]

    def test_no_evidence_at_all_is_context_only(self):
        assert et.tier_for([])["tier"] == et.CONTEXT_ONLY

    def test_a_widget_derived_restatement_is_its_own_pipeline(self):
        """The technology export arrives as one comma-joined cell and is also
        restated one vendor per cell. The token matcher finds the short form,
        so a rule matched on "Kaspersky" was reading as having no evidence."""
        assert et.tier_for(rows("technographic_map"))["pipelines"] == ["Technographics"]
        assert et.tier_for(rows("technographic_map", "technographics"))["pipeline_count"] == 1

    def test_an_unknown_dataset_is_not_a_pipeline(self):
        assert et.tier_for(rows("something_new"))["pipelines"] == []


class TestBannedOutputK1:
    """"BANNED: Recommend an active HP Poly motion solely because Cisco WebEx,
    TelePresence or other collaboration technologies are detected. ALLOWED:
    Treat collaboration technology as contextual evidence; do not prioritize a
    Poly opportunity unless separate current evidence supports it."

    The rule is not "never mention Poly" - it is that detected technology stops
    counting as corroboration once the category's own intent reads No Signal.
    """

    def test_detected_technology_alone_on_zero_intent_is_context(self):
        out = et.tier_for(rows("technographics"), category_intent=0)
        assert out["tier"] == et.CONTEXT_ONLY
        assert "banned output K1" in out["basis"]

    def test_the_no_signal_wording_counts_too(self):
        assert et.tier_for(rows("technographics"),
                           category_intent="No Signal")["tier"] == et.CONTEXT_ONLY

    def test_separate_current_evidence_still_lifts_it(self):
        """"unless separate current evidence supports it" - hiring or news is
        exactly that, and the rule demotes the technology, not the offering."""
        out = et.tier_for(rows("technographics", "job_openings"), category_intent=0)
        assert out["tier"] == et.CONVERSATION_STARTER
        assert out["corroborating_pipelines"] == ["Hiring"]

    def test_a_real_intent_score_leaves_technology_counting(self):
        out = et.tier_for(rows("technographics"), category_intent=34)
        assert out["tier"] == et.CONVERSATION_STARTER

    def test_an_unknown_score_is_not_read_as_zero(self):
        """"Missing data must remain missing. Absence of evidence does not mean
        No." An unscored category must not silently demote the evidence."""
        out = et.tier_for(rows("technographics"), category_intent=None)
        assert out["tier"] == et.CONVERSATION_STARTER
        assert out["technology_demoted_for_no_signal"] is None
