"""Matching an account's evidence to the rulebook - and refusing to.

The rulebook states four rules about how it may be used, and each one is a way
of NOT making a recommendation:

    C 01  the need must come from the account's own research
    C 06  one main recommendation; another only on separate evidence
    C 07  no rule, or an unmet condition -> leave it out or label it clearly
          ("Do not force a match")
    C 02  facts come from the rule, never from the original HP files

So nearly all of this tests the refusals. A wrong recommendation carries HP's
name to a customer; an absent one costs a seller nothing they did not already
lack.

Run: python -m pytest tests/test_rulebook_match.py -v
"""

import os
import sys
from typing import ClassVar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import rulebook as rb


def rule(label, family, tokens=(), terms=(), conditions=(), offering="An HP thing",
         order=1, part="B", **flags):
    return {
        "_id": "B::%s" % label.replace(" ", "-"),
        "kind": "rule", "part": part, "family": family, "rule_label": label,
        "order": order, "signal_text": "signal for %s" % label,
        "offering": offering, "allowed_facts": ["%s may be stated." % label],
        "prohibitions": ["Do not overstate %s." % label],
        "system_action": "Recommend %s." % offering,
        "conditions": list(conditions),
        "signal_tokens": list(tokens), "observable_terms": list(terms),
        "modifier_only": bool(flags.get("modifier_only")),
        "routing_only": bool(flags.get("routing_only")),
        "material": None,
    }


def routing(opportunity, families, tokens=(), terms=(), order=1):
    return {"_id": "routing::%s" % opportunity.lower().replace(" ", "-"),
            "kind": "routing", "opportunity_type": opportunity,
            "families": list(families), "order": order,
            "evidence_examples": "examples for %s" % opportunity,
            "signal_tokens": list(tokens), "observable_terms": list(terms)}


def book(rules=(), routes=(), matrices=None, country_lists=None):
    return {"rules": list(rules), "routing": list(routes),
            "matrices": matrices or {}, "guardrails": [],
            "country_lists": country_lists or {}}


def evidence(*texts):
    return [{"text": t} for t in texts]


BOOK = book(
    rules=[
        rule("WXP 01", "WXP", terms=["service desk", "manageengine"]),
        rule("WXP 02", "WXP", terms=["helpdesk ticket"], order=2),
        rule("WOLF 02", "WOLF", terms=["endpoint security"], order=1),
        rule("CARE 01", "CARE", terms=["onsite service"], order=1),
    ],
    routes=[
        routing("Workforce experience", ["WXP"],
                terms=["service desk", "helpdesk ticket", "manageengine"]),
        routing("Security", ["WOLF"], terms=["endpoint security"], order=2),
        routing("Support and Care Pack", ["CARE"], terms=["onsite service"], order=3),
    ])


class TestC01TheAccountsOwnEvidenceDecides:
    """"HP materials cannot prove that the account has a problem." The routing
    table is the outer gate, and a rule can never pull itself in."""

    def test_a_type_nothing_raises_does_not_fire(self):
        raised = rb.route(BOOK, evidence("We run ManageEngine for IT."))
        assert [r["opportunity_type"] for r in raised] == ["Workforce experience"]

    def test_rules_come_only_from_families_a_type_raised(self):
        matches = rb.candidates(BOOK, evidence("We run ManageEngine for IT."))
        assert {m["family"] for m in matches} == {"WXP"}

    def test_an_account_raising_nothing_gets_nothing(self):
        assert rb.route(BOOK, evidence("We sell tractors.")) == []
        assert rb.candidates(BOOK, evidence("We sell tractors.")) == []

    def test_no_evidence_at_all_is_not_an_error(self):
        assert rb.route(BOOK, []) == []
        assert rb.candidates(BOOK, None) == []

    def test_a_rule_whose_family_routed_still_needs_its_own_evidence(self):
        """The routing type opens the door; it does not admit every rule
        behind it. WXP 02 is about helpdesk tickets and nothing said so."""
        matches = rb.candidates(BOOK, evidence("We run ManageEngine for IT."))
        assert [m["rule_label"] for m in matches] == ["WXP 01"]

    def test_a_known_look_alike_does_not_fire_a_rule(self):
        """`GLOBAL_EXCLUDE_PHRASES` entries were all observed firing wrongly on
        real accounts."""
        noisy = book(
            rules=[rule("WOLF 02", "WOLF", terms=["tokenization"])],
            routes=[routing("Security", ["WOLF"], terms=["tokenization"])])
        assert rb.route(noisy, evidence("Our asset tokenization platform")) == []


class TestC07ConditionsAreDroppedOrLabelledNeverIgnored:

    US_ONLY: ClassVar[list] = [{
        "text": "Version 1.0 begins in the United States and in English.",
        "condition_type": "country"}]
    VAGUE: ClassVar[list] = [{
        "text": "Only where the commercial terms permit.",
        "condition_type": "unclassified"}]

    def test_a_condition_the_account_contradicts_drops_the_rule(self):
        b = book(rules=[rule("IQ 01", "IQ", terms=["copilot"], conditions=self.US_ONLY)],
                 routes=[routing("Enterprise AI", ["IQ"], terms=["copilot"])])
        assert rb.candidates(b, evidence("Copilot rollout"), None, "Indonesia") == []

    def test_the_same_condition_passes_where_it_is_satisfied(self):
        b = book(rules=[rule("IQ 01", "IQ", terms=["copilot"], conditions=self.US_ONLY)],
                 routes=[routing("Enterprise AI", ["IQ"], terms=["copilot"])])
        matches = rb.candidates(b, evidence("Copilot rollout"), None, "United States")
        assert [m["rule_label"] for m in matches] == ["IQ 01"]

    def test_a_condition_that_cannot_be_tested_is_labelled_not_enforced(self):
        """C 07's second branch. Silently passing it would be the easy bug;
        silently dropping on it would delete valid recommendations."""
        b = book(rules=[rule("CARE 01", "CARE", terms=["onsite"], conditions=self.VAGUE)],
                 routes=[routing("Support and Care Pack", ["CARE"], terms=["onsite"])])
        matches = rb.candidates(b, evidence("We need onsite cover"), None, "Indonesia")
        assert len(matches) == 1
        assert matches[0]["unverified_conditions"] == [self.VAGUE[0]["text"]]

    def test_an_unknown_country_labels_rather_than_drops(self):
        """Not knowing where an account is must not silently delete every rule
        that names a market."""
        satisfied, unmet, unverified = rb.check_conditions(
            {"conditions": self.US_ONLY}, evidence("x"), "")
        assert satisfied is True
        assert unmet == []
        assert len(unverified) == 1

    def test_a_device_condition_is_never_treated_as_testable(self):
        """It usually names the recommendation, not a requirement on the
        estate, so testing it would drop the rule whenever it was right."""
        conditions = [{"text": "Use EliteBook 6 G2 when the account needs AI.",
                       "condition_type": "device_family"}]
        satisfied, _unmet, unverified = rb.check_conditions(
            {"conditions": conditions}, evidence("x"), "Indonesia")
        assert satisfied is True
        assert len(unverified) == 1

    def test_an_environment_condition_is_satisfied_when_the_account_names_it(self):
        conditions = [{"text": "Requires Intune management.",
                       "condition_type": "management_environment"}]
        satisfied, _unmet, unverified = rb.check_conditions(
            {"conditions": conditions}, evidence("We manage devices with Intune"), "")
        assert satisfied is True
        assert unverified == []

    def test_a_missing_environment_is_labelled_not_counted_against_the_rule(self):
        """An export simply may not list it; absence is not contradiction."""
        conditions = [{"text": "Requires Intune management.",
                       "condition_type": "management_environment"}]
        satisfied, unmet, unverified = rb.check_conditions(
            {"conditions": conditions}, evidence("We run Windows"), "")
        assert satisfied is True
        assert unmet == []
        assert len(unverified) == 1


class TestC06OneMainRecommendation:

    def test_the_best_earned_rule_becomes_the_primary(self):
        matches = rb.candidates(
            BOOK, evidence("ManageEngine service desk", "service desk tooling"))
        chosen = rb.select(matches)
        assert chosen["primary"]["rule_label"] == "WXP 01"

    def test_a_second_rule_on_the_same_evidence_is_withheld(self):
        """"Add another product or service only when separate verified
        evidence supports it." One sentence is one recommendation."""
        b = book(
            rules=[rule("WXP 01", "WXP", terms=["service desk"]),
                   rule("WXP 02", "WXP", terms=["service desk"], order=2)],
            routes=[routing("Workforce experience", ["WXP"], terms=["service desk"])])
        chosen = rb.select(rb.candidates(b, evidence("Our service desk is busy")))
        assert chosen["primary"]["rule_label"] == "WXP 01"
        assert chosen["secondary"] == []
        assert chosen["withheld"][0]["rule_label"] == "WXP 02"

    def test_a_second_rule_on_separate_evidence_is_admitted(self):
        chosen = rb.select(rb.candidates(
            BOOK, evidence("We run ManageEngine", "Endpoint security review")))
        assert chosen["primary"]["rule_label"] == "WXP 01"
        assert [m["rule_label"] for m in chosen["secondary"]] == ["WOLF 02"]

    def test_a_modifier_rule_never_becomes_the_recommendation(self):
        """Seven of Part A's eighteen only qualify a choice already made.
        Promoting one is how "one main recommendation" quietly becomes eight."""
        b = book(rules=[rule("14", "HARDWARE", terms=["sustainability"],
                             part="A", modifier_only=True)],
                 routes=[routing("Lifecycle and sustainability", ["HARDWARE"],
                                 terms=["sustainability"])])
        chosen = rb.select(rb.candidates(b, evidence("Our sustainability report")))
        assert chosen["primary"] is None
        assert "qualifies another" in chosen["reason"]

    def test_a_routing_only_rule_never_becomes_the_recommendation(self):
        """WOLF 01 says in the document's own words: "Do not recommend a
        generic Wolf Security bundle"."""
        b = book(rules=[rule("WOLF 01", "WOLF", terms=["ransomware"],
                             routing_only=True)],
                 routes=[routing("Security", ["WOLF"], terms=["ransomware"])])
        chosen = rb.select(rb.candidates(b, evidence("ransomware incident")))
        assert chosen["primary"] is None

    def test_nothing_matched_says_so_rather_than_inventing(self):
        chosen = rb.select([])
        assert chosen["primary"] is None
        assert chosen["reason"] == "no rule fired"


class TestC02FactsComeFromTheRuleOnly:

    def test_the_facts_are_the_rules_own(self):
        matches = rb.candidates(BOOK, evidence("We run ManageEngine"))
        facts = rb.facts_for(matches[0])
        assert facts["allowed_facts"] == ["WXP 01 may be stated."]
        assert facts["fact_source"] == "rulebook"

    def test_prohibitions_travel_with_the_facts(self):
        """C 05 and the many "Do not name a tier" instructions are only useful
        if they reach the thing that writes the prose."""
        matches = rb.candidates(BOOK, evidence("We run ManageEngine"))
        assert rb.facts_for(matches[0])["prohibitions"]

    def test_unverified_conditions_travel_with_the_facts(self):
        b = book(rules=[rule("CARE 01", "CARE", terms=["onsite"],
                             conditions=[{"text": "Only where available.",
                                          "condition_type": "unclassified"}])],
                 routes=[routing("Support and Care Pack", ["CARE"], terms=["onsite"])])
        matches = rb.candidates(b, evidence("onsite cover needed"))
        assert rb.facts_for(matches[0])["unverified_conditions"]


class TestTheTwoFamilyGates:

    WOLF: ClassVar[dict] = {"wolf": [
        {"_id": "matrix::wolf::business", "kind": "matrix", "matrix": "wolf",
         "offering": "Wolf Security for Business", "order": 1,
         "columns": {"device support": "Eligible HP PCs only"}},
        {"_id": "matrix::wolf::pro", "kind": "matrix", "matrix": "wolf",
         "offering": "Wolf Pro Security", "order": 3,
         "columns": {"device support": "Supported HP and non-HP Windows PCs"}},
    ]}

    def test_an_estate_with_no_hp_clients_cannot_take_the_hp_only_offerings(self):
        """The matrix's device-support column is the gate, and G 17 forbids
        mixing conditions between offerings - so one row, not a blend."""
        chosen = rb.wolf_offering(book(matrices=self.WOLF), [], has_hp_clients=False)
        assert chosen["offering"] == "Wolf Pro Security"

    def test_an_hp_estate_may_take_the_narrower_one(self):
        chosen = rb.wolf_offering(book(matrices=self.WOLF), [], has_hp_clients=True)
        assert chosen["offering"] == "Wolf Security for Business"

    def test_no_matrix_means_no_offering_rather_than_a_guess(self):
        assert rb.wolf_offering(book(), [], has_hp_clients=True) is None

    def test_hp_iq_is_blocked_outside_its_launch_market(self):
        """Not unverifiable - unsatisfiable. Both live accounts are Indonesian,
        so all twelve IQ rules can never fire, and a seller should be told why
        rather than left wondering where HP IQ went."""
        result = rb.iq_availability(book(), "Indonesia")
        assert result["available"] is False
        assert "United States" in result["reason"]

    def test_hp_iq_is_available_in_its_launch_market(self):
        assert rb.iq_availability(book(), "United States")["available"] is True

    def test_an_unknown_country_is_not_a_block(self):
        assert rb.iq_availability(book(), "")["available"] is None


class TestATermMustEarnTheRuleNotMerelyPointAtIt:
    """C 07: "leave out the recommendation ... Do not force a match."

    Two ways a rule can fire on a term that proves nothing, both found on a
    real account after the revised rulebook was loaded.
    """

    def test_a_ubiquitous_platform_cannot_qualify_a_rule_by_itself(self):
        """PRINT 21 offers TROY secure cheque printing on a signal the rulebook
        words as "a verified secure check-printing or MICR requirement". It
        fired on "sap erp" - which describes what TROY integrates with, not a
        customer who prints cheques. Nearly every large account runs an ERP, so
        on that evidence the rule reaches nearly every large account."""
        b = book(rules=[rule("PRINT 21", "PRINT", terms=["sap erp"])],
                 routes=[routing("Print and scan", ["PRINT"])])
        assert rb.candidates(b, evidence("We run SAP ERP for finance")) == []

    def test_but_it_still_counts_once_the_rule_is_otherwise_earned(self):
        """Demoted, not deleted. "microsoft teams" qualifies no rule alone, yet
        it is real corroboration for a collaboration rule an account's own
        headset estate already earned."""
        b = book(rules=[rule("POLY 01", "POLY",
                             terms=["microsoft teams", "jabra headsets"])],
                 routes=[routing("Collaboration", ["POLY"])])
        got = rb.candidates(b, evidence("Jabra headsets and Microsoft Teams"))
        assert [m["rule_label"] for m in got] == ["POLY 01"]
        assert got[0]["qualifying_terms"] == ["jabra headsets"]
        assert got[0]["indicative_terms"] == ["microsoft teams"]

    def test_a_routing_only_rule_is_not_earned_by_its_own_wording(self):
        """PRINT 25's signal text enumerates the verticals it covers, so
        "financial services" is part of the RULE's wording, and its system
        action reads: "Treat industry as a routing signal only ... do not invent
        a vertical app or capability from the industry name alone." An account
        described as financial services has not thereby shown a document
        workflow need."""
        b = book(rules=[rule("PRINT 25", "PRINT",
                             tokens=["financial services"],
                             terms=["epic systems", "meditech"],
                             routing_only=True)],
                 routes=[routing("Print and scan", ["PRINT"])])
        assert rb.candidates(b, evidence("a financial services group")) == []
        got = rb.candidates(b, evidence("we run Meditech"))
        assert [m["rule_label"] for m in got] == ["PRINT 25"]

    def test_a_rule_with_no_observable_vocabulary_is_gated_not_deleted(self):
        """Observable terms are derived by a model at load time and a rule can
        end up with none. Requiring one there would remove the rule rather than
        gate it, so its own wording still stands."""
        b = book(rules=[rule("PRINT 26", "PRINT", tokens=["managed print"],
                             routing_only=True)],
                 routes=[routing("Print and scan", ["PRINT"])])
        assert [m["rule_label"]
                for m in rb.candidates(b, evidence("our managed print estate"))
                ] == ["PRINT 26"]

    def test_a_qualifier_that_narrows_keeps_the_term_specific(self):
        """The test is whether the term still names something an account might
        genuinely not have. "sap erp" is "sap"; "salesforce health cloud" is
        not "salesforce", because "health" narrows it to a product most
        accounts running Salesforce do not own."""
        assert rb.indicative_term("sap erp") is True
        assert rb.indicative_term("salesforce health cloud") is False
        assert rb.indicative_term("solidworks") is False


class TestTheFamilyCapCountsRecommendationsNotQualifiers:
    """`MAX_RULES_PER_FAMILY` limits how many recommendations one family may
    offer. Part A's eighteen rules all sit in the family "HARDWARE", so a
    modifier ranked inside the cap spent a slot no recommendation could use -
    and cut the rule HP's own "AI hiring" signal had just earned before
    `select` ever saw it."""

    def test_a_modifier_does_not_spend_a_recommendation_slot(self):
        rules = [rule("H %d" % i, "HARDWARE", terms=["autodesk"], order=i)
                 for i in range(1, rb.MAX_RULES_PER_FAMILY + 1)]
        rules.insert(1, rule("H MOD", "HARDWARE", terms=["autodesk"],
                             order=99, modifier_only=True))
        last = rule("H LAST", "HARDWARE", terms=["autodesk"], order=100)
        b = book(rules=rules + [last],
                 routes=[routing("Hardware", ["HARDWARE"])])
        got = [m["rule_label"] for m in rb.candidates(b, evidence("autodesk"))]
        # Every standalone rule up to the cap, plus the modifier alongside -
        # never the modifier instead of one of them.
        standalone = [label for label in got if label != "H MOD"]
        assert len(standalone) == rb.MAX_RULES_PER_FAMILY
        assert "H MOD" in got

    def test_the_cap_still_holds_for_recommendations(self):
        rules = [rule("H %d" % i, "HARDWARE", terms=["autodesk"], order=i)
                 for i in range(1, rb.MAX_RULES_PER_FAMILY + 4)]
        b = book(rules=rules, routes=[routing("Hardware", ["HARDWARE"])])
        got = rb.candidates(b, evidence("autodesk"))
        assert len(got) == rb.MAX_RULES_PER_FAMILY


class TestMatchingUsesBothVocabularies:
    """Signal tokens are anchored in the rulebook's words and fired nothing at
    all on a real account; observable terms are what the account's files
    actually say. A rule needs either."""

    def test_an_observable_term_fires_a_rule(self):
        b = book(rules=[rule("WXP 01", "WXP", tokens=["high ticket volume"],
                             terms=["manageengine"])],
                 routes=[routing("Workforce experience", ["WXP"],
                                 terms=["manageengine"])])
        assert rb.candidates(b, evidence("We use ManageEngine"))

    def test_the_rulebooks_own_wording_still_fires_when_it_appears(self):
        b = book(rules=[rule("WXP 01", "WXP", tokens=["high ticket volume"],
                             terms=["manageengine"])],
                 routes=[routing("Workforce experience", ["WXP"],
                                 tokens=["high ticket volume"])])
        assert rb.candidates(b, evidence("We have high ticket volume"))

    def test_a_rule_with_neither_can_never_fire(self):
        b = book(rules=[rule("WXP 01", "WXP")],
                 routes=[routing("Workforce experience", ["WXP"], terms=["x y"])])
        assert rb.candidates(b, evidence("x y")) == []


class TestCorpusVersionAndLoad:

    class FakeCollection:
        def __init__(self, docs, version=None):
            self.docs = docs
            self.version = version

        def find(self, _query, _projection=None):
            return iter(self.docs)

        def find_one(self, query, _projection=None):
            if query.get("_id") == rb.VERSION_DOC_ID:
                return {"knowledge_version": self.version} if self.version else None
            return None

    def _db(self, docs=(), version=None):
        return {rb.COLLECTION: self.FakeCollection(list(docs), version)}

    def test_the_version_is_reported_for_cache_fingerprints(self):
        assert rb.knowledge_version(self._db(version="abc")) == "abc"

    def test_an_unloaded_rulebook_reports_a_stable_empty_version(self):
        assert rb.knowledge_version(self._db()) == ""

    def test_a_broken_database_does_not_raise(self):
        class Exploding:
            def find_one(self, *_a, **_k):
                raise RuntimeError("no connection")

            def find(self, *_a, **_k):
                raise RuntimeError("no connection")

        assert rb.knowledge_version({rb.COLLECTION: Exploding()}) == ""
        assert rb.load({rb.COLLECTION: Exploding()})["rules"] == []

    def test_load_sorts_the_document_into_its_parts(self):
        loaded = rb.load(self._db([
            rule("WXP 01", "WXP"),
            routing("Workforce experience", ["WXP"]),
            {"_id": "guardrail::C-02", "kind": "guardrail", "scope": "common",
             "guardrail_id": "C 02", "order": 2, "rule_text": "..."},
            {"_id": "country_list::superlative", "kind": "country_list",
             "restriction": "superlative", "countries_folded": ["indonesia"]},
            {"_id": "matrix::wolf::pro", "kind": "matrix", "matrix": "wolf",
             "offering": "Wolf Pro Security", "order": 1, "columns": {}},
        ]))
        assert len(loaded["rules"]) == 1
        assert len(loaded["routing"]) == 1
        assert len(loaded["guardrails"]) == 1
        assert loaded["matrices"]["wolf"]
        assert rb.blocked_countries(loaded, "superlative") == {"indonesia"}


class TestHowWellARuleIsEarned:
    """Ranking decides which rule becomes the one recommendation a seller
    reads, so what it rewards matters more than it looks."""

    def test_distinct_terms_beat_raw_hit_count(self):
        """Counting cells rewards whichever rule owns the broadest term. On a
        real account one bare vendor name matched 40 technographics cells and
        carried a rule about an onboarding service past rules that three
        specific terms each pointed at."""
        b = book(
            rules=[rule("WXP 12", "WXP", terms=["widespread"]),
                   rule("WXP 07", "WXP", terms=["alpha", "beta", "gamma"], order=2)],
            routes=[routing("Workforce experience", ["WXP"],
                            terms=["widespread", "alpha"])])
        broad = evidence(*["widespread tooling %d" % i for i in range(40)])
        specific = evidence("alpha here", "beta here", "gamma here")
        matches = rb.candidates(b, broad + specific)
        assert matches[0]["rule_label"] == "WXP 07"
        assert len(matches[0]["matched_terms"]) == 3

    def test_hit_count_still_breaks_a_tie_between_equal_terms(self):
        b = book(
            rules=[rule("WXP 01", "WXP", terms=["alpha"]),
                   rule("WXP 02", "WXP", terms=["beta"], order=2)],
            routes=[routing("Workforce experience", ["WXP"],
                            terms=["alpha", "beta"])])
        matches = rb.candidates(b, evidence("alpha", "alpha again", "beta"))
        assert matches[0]["rule_label"] == "WXP 01"

    def test_the_matched_terms_are_reported_for_inspection(self):
        """A seller asking why a rule fired should be able to be told."""
        matches = rb.candidates(BOOK, evidence("We run ManageEngine"))
        assert matches[0]["matched_terms"] == ["manageengine"]


class TestWhatTheSellerIsShownAsACaveat:
    """`unverified_conditions` is C 07's label branch and appears on the card.
    It has to carry limits the reader needs, and not instructions aimed at
    whoever writes the copy."""

    def _facts(self, condition_text):
        b = book(rules=[rule("WXP 07", "WXP", terms=["power bi"],
                             conditions=[{"text": condition_text,
                                          "condition_type": "unclassified"}])],
                 routes=[routing("Workforce experience", ["WXP"], terms=["power bi"])])
        return rb.facts_for(rb.candidates(b, evidence("We run Power BI"))[0])

    def test_an_instruction_to_the_writer_is_not_shown_as_a_caveat(self):
        """Verbatim from WXP 07. Shown as an unverified condition it reads as a
        doubt about this account, which is not what it says."""
        facts = self._facts("Mention only the integration that matches the "
                            "account evidence.")
        assert facts["unverified_conditions"] == []

    def test_a_real_limit_is_still_shown(self):
        """Verbatim from WXP 11, and exactly what a seller needs to know."""
        text = ("This rulebook does not contain a capability-to-tier mapping, "
                "so the engine must not choose a tier automatically.")
        assert self._facts(text)["unverified_conditions"] == [text]

    def test_a_market_limit_is_still_shown(self):
        text = "Version 1.0 begins in the United States and in English."
        assert self._facts(text)["unverified_conditions"] == [text]

    def test_the_instruction_still_reaches_whoever_writes_the_copy(self):
        """It is dropped from the caveat list, not from the rule - the writer
        should still be told to be selective."""
        b = book(rules=[rule("WXP 07", "WXP", terms=["power bi"])],
                 routes=[routing("Workforce experience", ["WXP"], terms=["power bi"])])
        facts = rb.facts_for(rb.candidates(b, evidence("We run Power BI"))[0])
        assert facts["allowed_facts"]


class TestCatalogueEntriesNeverLead:
    """Seven rules say in their own words that the rulebook holds nothing
    about the offering - "This rulebook contains no deliverables, duration,
    response time, or service-level details for it". The offering is real and
    may be named, but there is nothing to say about it, so leading with one
    puts an empty card at the top of the page. WXP 12 did exactly that."""

    EMPTY: ClassVar[str] = ("HP Workforce Experience Platform Enhanced Onboarding "
                            "Service is an available named offering. This rulebook "
                            "contains no deliverables or service-level details for it.")

    def _book(self, empty_facts, solid_facts=None):
        rules = [dict(rule("WXP 12", "WXP", terms=["onboarding"]),
                      allowed_facts=[empty_facts])]
        if solid_facts:
            rules.append(dict(rule("WXP 07", "WXP", terms=["power bi"], order=2),
                              allowed_facts=[solid_facts]))
        return book(rules=rules,
                    routes=[routing("Workforce experience", ["WXP"],
                                    terms=["onboarding", "power bi"])])

    def test_a_catalogue_entry_is_recognised_from_its_own_words(self):
        assert rb._catalogue_only({"allowed_facts": [self.EMPTY]})
        assert not rb._catalogue_only(
            {"allowed_facts": ["Recommend Wolf Pro Security as primary antivirus."]})

    def test_it_never_becomes_the_recommendation(self):
        chosen = rb.select(rb.candidates(self._book(self.EMPTY),
                                         evidence("onboarding project")))
        assert chosen["primary"] is None
        assert "catalogue entry" in chosen["reason"]

    def test_a_rule_with_something_to_say_takes_the_slot_instead(self):
        b = self._book(self.EMPTY, "Recommend WXP where Power BI is already in use.")
        chosen = rb.select(rb.candidates(b, evidence("onboarding project", "power bi")))
        assert chosen["primary"]["rule_label"] == "WXP 07"

    def test_it_is_still_kept_as_a_qualifier(self):
        """The offering is real - a seller already discussing WXP may name it."""
        chosen = rb.select(rb.candidates(self._book(self.EMPTY),
                                         evidence("onboarding project")))
        assert [m["rule_label"] for m in chosen["modifiers"]] == ["WXP 12"]


class TestOnePlayPerOpportunityType:
    """C 06 reads "Give one main recommendation. Add ANOTHER product or service
    only when separate verified evidence supports it" - singular. With routing
    no longer gating families, Astra fired twelve Part B rules and four Care
    Pack rules could all have landed on one page, which is a catalogue."""

    def _book(self):
        return book(
            rules=[rule("CARE 01", "CARE", terms=["onsite"], order=1),
                   rule("CARE 05", "CARE", terms=["media retention"], order=5),
                   rule("WOLF 09", "WOLF", terms=["kaspersky"], order=9)],
            routes=[routing("Support and Care Pack", ["CARE"], terms=["onsite"]),
                    routing("Security", ["WOLF"], terms=["kaspersky"], order=2)])

    def test_a_second_rule_from_the_same_family_is_withheld(self):
        chosen = rb.select(rb.candidates(
            self._book(), evidence("onsite cover", "media retention", "kaspersky")))
        assert chosen["primary"]["rule_label"] == "CARE 01"
        assert [m["rule_label"] for m in chosen["secondary"]] == ["WOLF 09"]
        withheld = {m["rule_label"]: m["withheld_because"] for m in chosen["withheld"]}
        assert "already speaks for this opportunity type" in withheld["CARE 05"]

    def test_a_different_family_on_separate_evidence_is_admitted(self):
        chosen = rb.select(rb.candidates(
            self._book(), evidence("onsite cover", "kaspersky")))
        assert [m["family"] for m in chosen["secondary"]] == ["WOLF"]


class TestRoutingIsAPathNotAGate:
    """WOLF 09 matches on "kaspersky" and "symantec endpoint protection", both
    of which the account runs. The Security ROUTING row had drawn thinner
    wording the account does not use, so the family never opened and the rule
    was never consulted. Both vocabularies come from the same
    non-deterministic derivation, so which is better is luck."""

    def test_a_rule_fires_on_its_own_evidence_when_its_routing_row_does_not(self):
        b = book(rules=[rule("WOLF 09", "WOLF", terms=["kaspersky"])],
                 routes=[routing("Security", ["WOLF"], terms=["okta"])])
        matches = rb.candidates(b, evidence("We run Kaspersky"))
        assert [m["rule_label"] for m in matches] == ["WOLF 09"]

    def test_the_rule_still_needs_the_accounts_own_evidence(self):
        """Opening the routing gate must not mean every rule fires."""
        b = book(rules=[rule("WOLF 09", "WOLF", terms=["kaspersky"])],
                 routes=[routing("Security", ["WOLF"], terms=["okta"])])
        assert rb.candidates(b, evidence("We sell tractors")) == []


class TestAMarketBlockedFamilyIsNeverOffered:
    """IQ 01 gates the whole family - "an employee workflow covered by IQ 02 to
    IQ 11" - and G 14 puts Version 1.0 in the United States, in English. Where
    the market fails, no IQ rule is reachable."""

    def _book(self):
        return book(
            rules=[rule("IQ 04", "IQ", terms=["knowledge search"]),
                   rule("WXP 07", "WXP", terms=["power bi"], order=7)],
            routes=[routing("Enterprise AI", ["IQ"], terms=["knowledge search"]),
                    routing("Workforce experience", ["WXP"], terms=["power bi"], order=2)])

    def test_no_iq_rule_survives_outside_the_launch_market(self):
        matches = rb.candidates(self._book(),
                                evidence("knowledge search", "power bi"), None, "Indonesia")
        assert [m["rule_label"] for m in matches] == ["WXP 07"]

    def test_iq_rules_are_offered_inside_it(self):
        matches = rb.candidates(self._book(),
                                evidence("knowledge search", "power bi"),
                                None, "United States")
        assert {m["rule_label"] for m in matches} == {"IQ 04", "WXP 07"}


class TestThePerTypeCapIsAPartBRule:
    """Part B's nine families ARE the opportunity types, so one play each is
    right. Part A's eighteen rules share a single family called HARDWARE while
    naming eighteen different products, and applying the cap there allowed
    exactly one hardware recommendation ever."""

    def _part_a(self):
        return book(
            rules=[dict(rule("10", "HARDWARE", terms=["autodesk"], order=10),
                        part="A"),
                   dict(rule("2", "HARDWARE", terms=["fleet rollout"], order=2),
                        part="A")],
            routes=[routing("Enterprise AI", ["HARDWARE"],
                            terms=["autodesk", "fleet rollout"])])

    def test_two_part_a_products_on_separate_evidence_both_survive(self):
        """Which one leads is decided by the rulebook's own document order -
        both fire on one term here, so rule 2 precedes rule 10. What matters
        is that neither is withheld for sharing a family."""
        chosen = rb.select(rb.candidates(
            self._part_a(), evidence("autodesk seats", "fleet rollout planned")))
        surviving = [chosen["primary"]["rule_label"]] +             [m["rule_label"] for m in chosen["secondary"]]
        assert sorted(surviving) == ["10", "2"]
        assert chosen["withheld"] == []

    def test_part_a_still_obeys_the_disjoint_evidence_test(self):
        """C 06 literally: another product only on SEPARATE evidence."""
        b = book(rules=[dict(rule("10", "HARDWARE", terms=["autodesk"], order=10),
                             part="A"),
                        dict(rule("2", "HARDWARE", terms=["autodesk"], order=2),
                             part="A")],
                 routes=[routing("Enterprise AI", ["HARDWARE"], terms=["autodesk"])])
        chosen = rb.select(rb.candidates(b, evidence("autodesk seats")))
        assert chosen["secondary"] == []
        assert "the same evidence" in chosen["withheld"][0]["withheld_because"]


class TestACardsOfferingMustSuitItsLine:
    """A vendor card already names a broad HP line. The rulebook offering added
    beside it has to be the same product family, or the card shows two
    different HP products and the reader cannot tell which is being proposed.

    This is the forced match C 07 forbids: the Google Workspace card, whose
    line is Poly Collaboration, was given "WXP and WXP Collaboration" because
    WXP 08's terms happen to include Google Workspace.
    """

    def test_the_map_is_declared_for_every_line_that_may_draw_one(self):
        from app.services.extractors.tech_landscape import (
            HP_LINE_TO_RULEBOOK_FAMILIES,
        )
        families = {f for fs in HP_LINE_TO_RULEBOOK_FAMILIES.values() for f in fs}
        assert families <= {"WXP", "CARE", "LIFE", "DEPLOY", "POLY",
                            "PRINT", "SCAN", "INK", "IQ", "WOLF"}

    def test_a_security_line_reaches_only_wolf_rules(self):
        from app.services.extractors.tech_landscape import (
            HP_LINE_TO_RULEBOOK_FAMILIES,
        )
        assert HP_LINE_TO_RULEBOOK_FAMILIES["hp wolf security"] == ("WOLF",)

    def test_a_collaboration_line_does_not_reach_wxp(self):
        """The exact pairing that was wrong on screen."""
        from app.services.extractors.tech_landscape import (
            HP_LINE_TO_RULEBOOK_FAMILIES,
        )
        assert "WXP" not in HP_LINE_TO_RULEBOOK_FAMILIES["poly collaboration"]

    def test_an_undeclared_line_draws_nothing(self):
        """Safe direction: the card keeps the broad line it already had."""
        from app.services.extractors.tech_landscape import (
            HP_LINE_TO_RULEBOOK_FAMILIES,
        )
        assert HP_LINE_TO_RULEBOOK_FAMILIES.get("hp elite / pro pcs") is None


class TestTheOfferingVocabulary:
    """`filter_enum_list` gates every model-supplied product name in Content
    Messaging, Content Studio and the Opportunity Map, so adding to this list
    is the highest-regression change in the rulebook work. Adding never
    removes: every spelling that resolved before must still resolve."""

    ALREADY_ACCEPTED: ClassVar[list] = [
        "Z by HP Workstations", "HP Elite / Pro PCs", "HP EliteBook", "HP ProBook",
        "HP Wolf Security", "Poly Collaboration", "Poly Studio",
        "HP Enterprise Print / MPS", "HP Enterprise Printing & MPS",
        "HP Anyware / DaaS", "HP Anyware", "HP DaaS",
        "HP Elite", "HP Pro PCs", "Wolf Security", "Poly",
    ]

    def test_no_previously_accepted_spelling_stops_resolving(self):
        from app.services.extractors.grounding import normalize_hp_product
        for spelling in self.ALREADY_ACCEPTED:
            assert normalize_hp_product(spelling), spelling

    def test_the_rulebooks_service_families_now_have_a_line(self):
        """Three rules matched the Google Workspace card and all three were
        discarded because WXP and IQ had no word in the taxonomy."""
        from app.services.extractors.grounding import normalize_hp_product
        from app.services.extractors.tech_landscape import (
            RULEBOOK_FAMILY_TO_HP_LINE,
        )
        for family in ("WXP", "CARE", "LIFE", "DEPLOY", "IQ",
                       "WOLF", "POLY", "PRINT", "SCAN", "INK"):
            line = RULEBOOK_FAMILY_TO_HP_LINE.get(family)
            assert line, family
            assert normalize_hp_product(line) == line, family

    def test_an_offering_resolves_to_its_family_line(self):
        """The rulebook's own wording, as its rules write it."""
        from app.services.extractors.grounding import normalize_hp_product
        for offering, line in (
            ("WXP and WXP Collaboration", "HP Workforce Experience Platform"),
            ("Next Business Day", "HP Care Pack Services"),
            ("Device Life Extension", "HP Lifecycle & Sustainability Services"),
            ("HP Imaging Service", "HP Deployment & Configuration Services"),
            ("Ask IQ", "HP IQ for Enterprise"),
        ):
            assert normalize_hp_product(offering) == line, offering

    def test_a_competitor_still_resolves_to_nothing(self):
        """The reason this gate exists: a claim naming no HP line routes to the
        ACCOUNT corpus, so a competitor slipping through would be verified
        against the wrong evidence entirely."""
        from app.services.extractors.grounding import normalize_hp_product
        for name in ("Lenovo ThinkPad", "Dell Latitude", "Apple MacBook"):
            assert normalize_hp_product(name) is None, name


class TestTheWolfMatrixIsTheGate:
    """WOLF 01: "Choose the offering using the segment, device support,
    licence, management model, and capabilities written in WOLF 02 to WOLF 20
    and the selection matrix below. Do not recommend a generic Wolf Security
    bundle."

    The matrix was parsed and tested and never consulted in production. Two of
    its four offerings need HP client hardware, and the live account has none.
    """

    MATRIX: ClassVar[dict] = {"wolf": [
        {"offering": "Wolf Security for Business", "order": 1,
         "columns": {"device support": "Eligible HP PCs only"}},
        {"offering": "Wolf Pro Security Edition", "order": 2,
         "columns": {"device support": "Select HP commercial PCs only"}},
        {"offering": "Wolf Pro Security", "order": 3,
         "columns": {"device support": "Supported HP and non-HP Windows PCs"}},
    ]}

    def test_an_hp_only_offering_is_blocked_without_hp_hardware(self):
        b = book(matrices=self.MATRIX)
        assert not rb.wolf_offering_allowed(b, "Wolf Security for Business", False)
        assert rb.wolf_offering_allowed(b, "Wolf Pro Security", False)

    def test_the_longer_name_wins_the_lookup(self):
        """"Wolf Pro Security" is a substring of "Wolf Pro Security Edition",
        so matching in matrix order answered the Edition's question with the
        base product's row - and the Edition is the restricted one."""
        b = book(matrices=self.MATRIX)
        assert not rb.wolf_offering_allowed(b, "Wolf Pro Security Edition", False)

    def test_everything_is_allowed_on_an_hp_estate(self):
        b = book(matrices=self.MATRIX)
        for row in self.MATRIX["wolf"]:
            assert rb.wolf_offering_allowed(b, row["offering"], True)

    def test_an_offering_the_matrix_does_not_list_is_allowed(self):
        """The rules name offerings the four-row matrix does not, and refusing
        those would suppress rules the document intends to be usable."""
        assert rb.wolf_offering_allowed(book(matrices=self.MATRIX),
                                        "Sure Click Enterprise", False)

    def test_a_blocked_offering_never_becomes_a_candidate(self):
        b = book(
            rules=[rule("WOLF 02", "WOLF", terms=["kaspersky"],
                        offering="Wolf Security for Business"),
                   rule("WOLF 09", "WOLF", terms=["kaspersky"], order=9,
                        offering="Wolf Pro Security")],
            routes=[routing("Security", ["WOLF"], terms=["kaspersky"])],
            matrices=self.MATRIX)
        labels = [m["rule_label"] for m in rb.candidates(b, evidence("We run Kaspersky"))]
        assert labels == ["WOLF 09"]

    def test_hp_hardware_is_read_from_the_accounts_own_evidence(self):
        assert rb.has_hp_client_hardware(evidence("HP EliteBook 840", "Kaspersky"))
        assert not rb.has_hp_client_hardware(evidence("Microsoft Windows OS",
                                                      "Kaspersky"))
