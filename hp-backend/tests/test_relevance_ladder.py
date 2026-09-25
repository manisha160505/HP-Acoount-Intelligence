"""The client's relevance ladder, 25 Sep email.

    "Technology only (for example Intune/ServiceNow): an internal 'possible
     fit' only, NOT recommended.
     Technology plus related account evidence: 'HP WXP may be relevant to this
     opportunity.'
     A clear opportunity plus the Rulebook's conditions supported: 'HP WXP is
     relevant to this opportunity.'"
     "A Rulebook condition that cannot be evaluated counts as unmet. The
     offering can reach 'may be relevant' but never 'is relevant'."

Two things are pinned here: which rung a tier earns, and that prose claiming a
higher rung than its evidence is rejected.

Run: python -m pytest tests/test_relevance_ladder.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import evidence_tier as et
from app.services.hp.guardrails import tier_language_faults


class TestWhichRungATierEarns:

    def test_two_pipelines_reach_is_relevant(self):
        assert et.relevance_for(et.OPPORTUNITY) == et.RELEVANCE_IS

    def test_one_pipeline_reaches_may_be_relevant(self):
        assert et.relevance_for(et.CONVERSATION_STARTER) == et.RELEVANCE_MAY

    def test_context_only_is_not_recommended_at_all(self):
        assert et.relevance_for(et.CONTEXT_ONLY) == et.RELEVANCE_NOT_RECOMMENDED

    def test_an_unevaluable_condition_caps_at_may_be_relevant(self):
        """Rule 5. The live example is the Care Pack seat count: the data
        carries an employee band, never a seat count, so that condition can
        never be tested and must not produce a settled claim."""
        assert et.relevance_for(et.OPPORTUNITY, conditions_unevaluable=True) == et.RELEVANCE_MAY

    def test_the_cap_cannot_promote_a_lower_rung(self):
        assert et.relevance_for(et.CONTEXT_ONLY, conditions_unevaluable=True) == \
            et.RELEVANCE_NOT_RECOMMENDED


class TestProseIsHeldToItsRung:

    def test_is_relevant_is_rejected_on_one_pipeline(self):
        faults = tier_language_faults("HP WXP is relevant to this opportunity.",
                                      et.CONVERSATION_STARTER)
        assert faults and "settled relevance" in faults[0]

    def test_may_be_relevant_is_the_permitted_phrasing_there(self):
        assert tier_language_faults("HP WXP may be relevant to this opportunity.",
                                    et.CONVERSATION_STARTER) == []

    def test_is_relevant_is_allowed_at_the_opportunity_tier(self):
        assert tier_language_faults("HP WXP is relevant to this opportunity.",
                                    et.OPPORTUNITY) == []

    def test_context_only_may_not_recommend(self):
        faults = tier_language_faults("We recommend HP WXP for this estate.",
                                      et.CONTEXT_ONLY)
        assert faults and "must not be recommended" in faults[0]

    def test_context_only_may_still_name_an_integration_route(self):
        """The wording the client asked for by name, and it must survive."""
        assert tier_language_faults(
            "Intune detected; possible WXP integration route.",
            et.CONTEXT_ONLY) == []

    def test_an_hp_product_condition_survives_every_rung(self):
        """"Wolf Pro Security requires a supported Windows PC" is HP stating a
        product condition, not a claim about the account."""
        assert tier_language_faults(
            "Wolf Pro Security requires a supported Windows PC.",
            et.CONTEXT_ONLY) == []

    def test_an_account_need_is_still_rejected_below_opportunity(self):
        faults = tier_language_faults("Astra requires endpoint protection.",
                                      et.CONVERSATION_STARTER)
        assert faults and "confirmed need" in faults[0]
