"""Reading the HP 220 Account Rulebook without changing what it says.

The rulebook decides which HP offering a seller may put in front of a customer
and what they may claim about it. Everything a user will ever see is therefore
stored verbatim, or split from verbatim text by a rule written in the loader;
the one derived field is `signal_tokens`, which is a matching aid and is never
displayed.

So most of what follows tests the seams where a parse could quietly change
meaning - a table read as the wrong kind, a family dropped, a condition treated
as checkable when it is not, a model-suggested token that drifts off subject.
Each of the first three is a bug this file caught while it was being written.

The document itself is gitignored (`*.gitignore:30`), exactly like the HP decks
`extract_hp_decks.py` reads. The logic is therefore tested against inline
fixtures and always runs; the real counts are pinned in one class that skips
when the file is not there.

Run: python -m pytest tests/test_rulebook_parse.py -v
"""

import importlib.util
import os
import sys
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

_LOADER = os.path.join(os.path.dirname(__file__), "..", "scripts", "load_rulebook.py")
_spec = importlib.util.spec_from_file_location("load_rulebook", _LOADER)
rb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb)


class TestTheSignalTokenGate:
    """The one field a model contributes to. The gate is what makes that safe:
    the model may suggest wording, it may not introduce a subject."""

    SIGNAL = "Verified phishing, ransomware, malware, or stolen-device need"

    def test_a_token_from_the_rules_own_words_is_kept(self):
        kept, _rejected = rb._gate_tokens(["ransomware exposure"], self.SIGNAL)
        assert kept == ["ransomware exposure"]

    def test_an_ordinary_modifier_may_be_added(self):
        """"phishing incidents" for a rule that says "phishing" is a narrower
        phrasing - it can only ever match less, never something else. An
        earlier gate required every word to be anchored and threw away 476 of
        ~700 proposals, nearly all of them for this."""
        kept, _rejected = rb._gate_tokens(["phishing incidents"], self.SIGNAL)
        assert kept == ["phishing incidents"]

    def test_a_vendor_the_rule_does_not_name_is_rejected(self):
        """The one way a token could change what a rule is about. A Wolf
        Security rule must not come to match CrowdStrike."""
        kept, rejected = rb._gate_tokens(
            ["crowdstrike ransomware protection"], self.SIGNAL)
        assert kept == []
        assert "crowdstrike" in rejected[0]

    def test_a_token_about_something_else_entirely_is_rejected(self):
        kept, rejected = rb._gate_tokens(["office printer leasing"], self.SIGNAL)
        assert kept == []
        assert "signal" in rejected[0]

    def test_bare_generic_words_are_rejected(self):
        """A token that matches every company's files identifies nothing."""
        for token in ("security management", "device technology"):
            kept, _rejected = rb._gate_tokens([token], "security device management technology")
            assert kept == [], token

    def test_a_known_false_positive_is_rejected(self):
        """Every entry of GLOBAL_EXCLUDE_PHRASES was observed matching the
        wrong thing on a real account."""
        kept, rejected = rb._gate_tokens(
            ["executive development programme"],
            "Executive development programme for senior leaders")
        assert kept == []
        assert "false positive" in rejected[0]

    def test_tokens_are_bounded_and_deduplicated(self):
        kept, _r = rb._gate_tokens(
            ["ransomware", "ransomware exposure", "ransomware exposure"], self.SIGNAL)
        assert kept == ["ransomware exposure"]        # the single word is dropped

    def test_a_bare_number_never_becomes_a_token(self):
        """"1,000 or more PC seats" split into "1" and "000", and "000" then
        read as a figure the source never stated."""
        assert "000" not in rb._content_words("1,000 or more PC seats")

    def test_trailing_punctuation_is_stripped(self):
        """A stored token of "value sensitivity." would never be found in a
        file that says "value sensitivity"."""
        assert rb._content_words("or value sensitivity.") == ["value", "sensitivity"]


class TestObservableTerms:
    """What the account's own files would say if a rule's signal were true.
    A looser gate than the signal tokens - naming things the rule's wording
    does not is the entire point - so the specificity checks carry the weight."""

    def test_a_concrete_term_is_kept(self):
        kept, _r = rb._gate_terms(["manageengine", "service desk analyst"])
        assert kept == ["manageengine", "service desk analyst"]

    def test_a_bare_ubiquitous_vendor_name_is_rejected(self):
        """"microsoft" was the single term firing WXP 12, matched 40
        technographics cells on a real account, and made an onboarding service
        that account's top recommendation - for a rule whose own text says the
        rulebook holds no details about it."""
        kept, rejected = rb._gate_terms(["microsoft"])
        assert kept == []
        assert "every enterprise runs it" in rejected[0]

    def test_the_same_vendor_qualified_is_kept(self):
        """The rule is about the bare word, not the vendor: "microsoft intune"
        names something specific and should fire."""
        kept, _r = rb._gate_terms(["microsoft intune", "windows autopilot"])
        assert kept == ["microsoft intune", "windows autopilot"]

    def test_a_term_spanning_too_many_families_is_pruned(self):
        """Deterministic, and it catches what no per-rule gate can see: a term
        specific enough on its own is useless once four unrelated families
        claim it."""
        items = [{"family": f, "rule_label": "%s 01" % f,
                  "observable_terms": ["windows upgrade", "only mine %s" % f]}
                 for f in ("WXP", "CARE", "DEPLOY", "WOLF")]
        dropped = rb.prune_overbroad(items)   # 4 families > the limit of 3
        assert all("windows upgrade" not in i["observable_terms"] for i in items)
        assert all(len(i["observable_terms"]) == 1 for i in items)
        assert dropped

    def test_routing_rows_are_exempt_from_the_prune(self):
        """A routing type's terms overlap its own family's rules by design -
        that is how the door opens. Counting each routing row as a family of
        its own dropped 447 terms and left every type unable to fire."""
        rules = [{"family": f, "rule_label": "%s 01" % f,
                  "observable_terms": ["shared term"]}
                 for f in ("WXP", "CARE")]
        routes = [{"opportunity_type": "Workforce experience",
                   "observable_terms": ["shared term"]}]
        rb.prune_overbroad(rules, routes)
        assert routes[0]["observable_terms"] == ["shared term"]
        assert all(r["observable_terms"] == ["shared term"] for r in rules)

    def test_a_term_many_rules_of_ONE_family_share_survives(self):
        """Twenty Care Pack rules sharing a term is one opportunity described
        twenty ways, not an over-broad term."""
        items = [{"family": "CARE", "rule_label": "CARE %02d" % i,
                  "observable_terms": ["onsite response"]} for i in range(1, 21)]
        rb.prune_overbroad(items)
        assert all(i["observable_terms"] == ["onsite response"] for i in items)


class TestConditionsAndWhatMayBeChecked:
    """C 07 has two branches: drop the rule when a condition fails, or label it
    when it cannot be tested. Getting a condition into the wrong branch is the
    difference between a silent deletion and an honest note."""

    def test_a_country_condition_is_testable(self):
        assert rb.classify_condition(
            "Version 1.0 begins in the United States and in English.") == "country"

    def test_a_device_condition_is_labelled_not_tested(self):
        """Part A rule 2 reads "Use EliteBook 6 G2 when the account needs
        enterprise AI across a large fleet". Testing that as "the account must
        already run EliteBook 6 G2" would drop the rule every time it is
        right, so device conditions are labelled instead."""
        assert rb.classify_condition(
            "Use EliteBook 6 G2 when the account needs enterprise AI"
        ) == "device_family"
        assert "device_family" not in rb.TESTABLE_CONDITION_TYPES

    def test_an_unreadable_condition_defaults_to_not_testable(self):
        """The half of C 07 that is easy to lose: a condition nobody taught
        the loader to read must surface as unverified, never quietly pass."""
        assert rb.classify_condition(
            "Only where the stated commercial terms permit it."
        ) not in rb.TESTABLE_CONDITION_TYPES

    def test_every_condition_type_is_in_the_closed_vocabulary(self):
        declared = {name for name, _patterns in rb.CONDITION_TYPES} | {"unclassified"}
        assert declared >= rb.TESTABLE_CONDITION_TYPES

    def test_a_prohibition_never_appears_in_both_halves(self):
        """The card quoted the whole System action under "What HP says" and
        then repeated its negative clause under "Do not say". Both boxes were
        right and the card read as sloppy, so the clause is lifted out of the
        fact rather than copied from it."""
        facts, prohibitions, _c = rb.split_rule_text(
            "", "Treat WXP Collaboration as a separate licence; do not present "
                "it as included in every WXP licence.")
        assert facts == ["Treat WXP Collaboration as a separate licence."]
        assert prohibitions == ["Do not present it as included in every WXP licence."]
        assert not any(p in f for f in facts for p in prohibitions)

    def test_lifting_a_clause_out_leaves_no_dangling_punctuation(self):
        """The semicolon that joined the two halves goes with the clause."""
        facts, _p, _c = rb.split_rule_text(
            "", "Keep them apart; never merge the two.")
        assert facts == ["Keep them apart."]

    def test_a_sentence_that_is_wholly_a_prohibition_leaves_no_fact_behind(self):
        facts, prohibitions, _c = rb.split_rule_text(
            "", "Recommend it widely. Do not name a tier.")
        assert facts == ["Recommend it widely."]
        assert prohibitions == ["Do not name a tier."]

    def test_a_prohibition_is_not_something_the_engine_may_say(self):
        facts, prohibitions, _conditions = rb.split_rule_text(
            "", "Recommend HP Imaging Service. Do not name a tier.")
        assert prohibitions == ["Do not name a tier."]
        assert all("Do not" not in f for f in facts)

    def test_a_prohibition_still_contributes_its_condition(self):
        """A prohibition often carries the condition that triggers it, and
        C 07 has to see it rather than only the instruction to withhold."""
        _facts, prohibitions, conditions = rb.split_rule_text(
            "", "Use for basic containment. Do not use it unless the PC is "
                "eligible HP commercial hardware.")
        assert len(prohibitions) == 1
        assert any("eligible" in c["text"] for c in conditions)

    def test_a_prohibition_with_no_condition_yields_none(self):
        """"Do not use for non-HP PCs." states no testable condition, and
        inventing one from it would be reading in more than it says. The
        prohibition itself is still stored and shown."""
        _facts, prohibitions, conditions = rb.split_rule_text(
            "", "Use for basic containment. Do not use for non-HP PCs.")
        assert prohibitions == ["Do not use for non-HP PCs."]
        assert conditions == []

    def test_part_b_reads_its_facts_out_of_the_system_action(self):
        """Part B has no facts column at all - the action text IS the corpus."""
        facts, _p, _c = rb.split_rule_text(
            "", "Recommend Device Life Extension. HP collects the existing PCs.")
        assert len(facts) == 2

    def test_part_a_reads_its_facts_from_its_own_column(self):
        facts, _p, _c = rb.split_rule_text(
            "Intel Core Ultra; up to 50 TOPS NPU; HP Wolf Security", "Consider it.")
        assert facts == ["Intel Core Ultra", "up to 50 TOPS NPU", "HP Wolf Security"]


class TestFlagsCarriedFromTheShippedTable:
    """Seven of Part A's eighteen rules may never become a recommendation on
    their own. The rulebook has no column saying so; `product_rules.RULES`,
    transcribed from an earlier document and in production since, does."""

    def test_the_shipped_flags_are_available_to_the_loader(self):
        assert rb.PART_A_CARRIED, "no flags carried across"
        modifiers = {rid for rid, f in rb.PART_A_CARRIED.items() if f["modifier_only"]}
        assert modifiers == {6, 7, 14, 15, 16, 18}
        routing = {rid for rid, f in rb.PART_A_CARRIED.items() if f["routing_only"]}
        assert routing == {17}

    def test_the_hard_won_extras_survive_the_port(self):
        """Part A states none of these, and each was learned the hard way."""
        assert rb.PART_A_CARRIED[8]["requires_exact_competitor"] is True
        assert rb.PART_A_CARRIED[4]["roster_signal"] == "C-Suite"
        assert rb.PART_A_CARRIED[17]["roster_signal"] == "any"

    def test_reading_the_text_alone_would_have_got_rule_1_wrong(self):
        """Rule 1's action says "Do not choose it from an AI signal alone" - a
        caution, not a demotion. Deriving the flag from wording demoted the
        platform's main AI play; the shipped table is why it is not demoted."""
        read = rb.derive_flags(
            "Enterprise AI / local AI, AI adoption, Copilot rollout",
            "HP EliteBook 8 G2 Series",
            "For knowledge workers with strong AI needs, consider EliteBook 8 G2. "
            "Do not choose it from an AI signal alone; the user type must also fit.")
        assert read["modifier_only"] is True                  # what the text reads
        assert rb.PART_A_CARRIED[1]["modifier_only"] is False  # what ships


class TestTheTablesAreToldApart:
    """Two tables were read as the wrong kind while this was being written, and
    neither failed loudly - one merged two guardrail sets, the other dropped
    three rules. Both are pinned here."""

    class _Cell:
        def __init__(self, text):
            self.text = text

    class _Row:
        def __init__(self, cells):
            self.cells = [TestTheTablesAreToldApart._Cell(c) for c in cells]

    class _Table:
        def __init__(self, header):
            self.rows = [TestTheTablesAreToldApart._Row(header)]

    def _identify(self, header):
        return rb._identify(self._Table(header))

    def test_the_service_guardrails_are_not_read_as_common_ones(self):
        """"ID | Area | Simple rule" and "ID | Area | Rule" differ by one word,
        and a substring test let the common signature claim both."""
        assert self._identify(["ID", "Area", "Simple rule"]) == "guardrail_service"
        assert self._identify(["ID", "Area", "Rule"]) == "guardrail_common"

    def test_part_a_is_not_read_as_part_b(self):
        assert self._identify(
            ["Rule", "Account signal / condition", "HP material used",
             "HP facts available to the engine", "System action"]) == "part_a"
        assert self._identify(
            ["Rule", "Verified account signal", "HP offering to consider",
             "System action"]) == "part_b"

    def test_an_unknown_table_is_reported_rather_than_guessed_at(self):
        assert self._identify(["Something", "Entirely New"]) is None


class TestFamiliesAndRouting:

    def test_ink_is_the_tenth_family(self):
        """The revision added INK 01-06 from the Original HP Ink Portfolio."""
        assert "INK" in rb.PART_B_FAMILIES
        assert len(rb.PART_B_FAMILIES) == 10

    def test_ink_is_reached_through_print_and_scan(self):
        """The client added the rules without extending the eight-row routing
        table. Ink sits in the document's print section and shares its
        sources, so it is reached there rather than through a ninth
        opportunity type we would have had to invent."""
        assert set(rb.ROUTING_TO_FAMILIES["print and scan"]) == {
            "PRINT", "SCAN", "INK"}

    def test_scan_is_a_family_of_its_own(self):
        """The "Print and scan solution rules" table holds PRINT 01-03 and
        SCAN 01-03. Reading the section heading rather than the rule labels
        filed three scan rules under print and lost them."""
        assert "SCAN" in rb.PART_B_FAMILIES
        assert "PRINT" in rb.PART_B_FAMILIES

    def test_print_and_scan_routing_reaches_its_families(self):
        assert {"PRINT", "SCAN"} <= set(rb.ROUTING_TO_FAMILIES["print and scan"])

    def test_every_part_b_family_is_reachable_from_the_routing_table(self):
        """A family no routing type reaches is loaded and can never fire."""
        routed = {f for families in rb.ROUTING_TO_FAMILIES.values() for f in families}
        assert set(rb.PART_B_FAMILIES) == routed


class TestCountryLists:
    """Both live accounts are Indonesian, so these are not theoretical."""

    HEADER: ClassVar[list] = ["Restriction type",
                              "Exact countries/regions to block for the affected claim"]

    def _parse(self, label, cell):
        return rb._handle_country_list([[label, cell]], [rb._fold(h) for h in self.HEADER])

    def test_the_instruction_before_the_colon_is_not_a_country(self):
        out = self._parse("Superlative claims",
                          "Block the affected superlative claim in: Romania; Turkey; Indonesia.")
        assert out[0]["countries"] == ["Romania", "Turkey", "Indonesia"]

    def test_a_parenthetical_is_an_alias_not_part_of_the_name(self):
        out = self._parse("Superlative claims",
                          "Block in: United Arab Emirates (UAE); Indonesia.")
        assert "United Arab Emirates" in out[0]["countries"]
        assert out[0]["aliases"].get("uae") == "united arab emirates"

    def test_instructions_after_the_last_country_are_not_read_as_one(self):
        """The competitor cell runs its last country straight into a paragraph
        of instruction, and the whole string was stored as a country name."""
        out = self._parse(
            "Competitor claims",
            "Block in: Turkey; Mexico. Also block in any CIS country covered "
            "by the playbook restriction. Store it as a market-level block.")
        assert out[0]["countries"] == ["Turkey", "Mexico"]
        assert any("CIS country" in n for n in out[0]["notes"])

    def test_a_curly_apostrophe_folds_to_a_straight_one(self):
        """The document writes "Cote d'Ivoire" curly and the constants
        straight, so they compared as two different countries."""
        out = self._parse("Competitor claims", "Block in: Côte d’Ivoire.")
        assert "cote d'ivoire" in out[0]["countries_folded"]

    def test_accents_are_folded_so_the_ascii_constants_still_match(self):
        """The document writes "Reunion (France)" and "Cote d'Ivoire" with
        accents; the codebase's country constants are ASCII."""
        out = self._parse("Competitor claims", "Block in: Réunion (France); Turkey.")
        assert "reunion" in out[0]["countries_folded"]


@pytest.mark.skipif(not Path(rb.DEFAULT_DOCX).is_file(),
                    reason="the rulebook is gitignored, like the HP decks")
class TestTheRealDocument:
    """Counts pinned against the supplied file. A revision that changes them
    should fail here and be looked at, not load silently."""

    @pytest.fixture(scope="class")
    def parsed(self):
        docs, report = rb.parse(rb.DEFAULT_DOCX, use_model=False)
        return docs, report

    def test_every_table_is_recognised(self, parsed):
        _docs, report = parsed
        assert report["unmatched"] == []

    def test_the_rule_counts_match_the_document(self, parsed):
        docs, _report = parsed
        counts = {}
        for d in docs:
            if d["kind"] == "rule":
                counts[d["family"]] = counts.get(d["family"], 0) + 1
        assert counts == {"HARDWARE": 18, "WXP": 13, "CARE": 20, "LIFE": 4,
                          "DEPLOY": 15, "POLY": 5, "PRINT": 39, "SCAN": 10,
                          "INK": 6, "IQ": 12, "WOLF": 20}
        assert sum(counts.values()) == 162
        assert sum(v for k, v in counts.items() if k != "HARDWARE") == 144

    def test_the_supporting_blocks_are_all_there(self, parsed):
        docs, _report = parsed
        kinds = {}
        for d in docs:
            key = "%s:%s" % (d["kind"], d.get("scope") or d.get("matrix") or "")
            kinds[key] = kinds.get(key, 0) + 1
        assert kinds["routing:"] == 8
        assert kinds["matrix:wolf"] == 4
        assert kinds["matrix:iq"] == 4
        assert kinds["guardrail:common"] == 16      # C 01-C 16
        assert kinds["schema:"] == 12               # the 12-field C 11 record
        assert kinds["guardrail:product"] == 8
        assert kinds["guardrail:service"] == 12
        assert kinds["country_list:"] == 2

    def test_the_governing_guardrails_survive_verbatim(self, parsed):
        """C 02, C 06 and C 07 decide what the engine may do at all. If a parse
        ever mangles one, it must be visible here rather than in a card."""
        docs, _report = parsed
        text = {d["guardrail_id"]: d["rule_text"]
                for d in docs if d["kind"] == "guardrail"}
        assert "must not reopen the original HP files" in text["C 02"]
        assert "Give one main recommendation" in text["C 06"]
        # C 07's rule text states the two branches; "Do not force a match"
        # is its Area heading, which is carried separately.
        assert ("leave out the recommendation or label the missing condition"
                in text["C 07"])
        areas = {d["guardrail_id"]: d["area"]
                 for d in docs if d["kind"] == "guardrail"}
        assert "force a match" in (areas["C 07"] or "").lower()

    def test_provenance_sources_are_marked_as_never_read_at_runtime(self, parsed):
        """C 02: source names are provenance only."""
        docs, _report = parsed
        sources = [d for d in docs if d["kind"] == "source"]
        assert sources
        assert all(d["runtime_use"] is False for d in sources)

    def test_every_rule_can_fire_and_has_something_to_say(self, parsed):
        docs, _report = parsed
        for rule in [d for d in docs if d["kind"] == "rule"]:
            assert rule["signal_text"], rule["rule_label"]
            assert rule["allowed_facts"], rule["rule_label"]

    def test_the_revision_is_purely_additive(self, parsed):
        """The whole basis of this load. The client added print, scan and ink
        rules and changed none of the 113 that were already there - so a rule
        that existed before must load with its text untouched, or something
        other than the document has moved."""
        docs, _report = parsed
        rules = {d["rule_label"]: d for d in docs if d["kind"] == "rule"}
        assert len(rules) == 162
        # Every pre-existing family still has its original rules, unflagged.
        old_rules = [r for r in rules.values() if not r.get("is_new")]
        assert len(old_rules) == 113

    def test_exactly_the_highlighted_rules_are_flagged_new(self, parsed):
        """The client highlights a revision's additions in yellow, and the
        loader reads that rather than guessing from a diff."""
        docs, _report = parsed
        new = [d for d in docs if d["kind"] == "rule" and d.get("is_new")]
        assert len(new) == 49
        families = {}
        for rule in new:
            families[rule["family"]] = families.get(rule["family"], 0) + 1
        assert families == {"PRINT": 36, "SCAN": 7, "INK": 6}

    def test_every_rule_carries_its_evidence_source(self, parsed):
        """C 12: "Use only HP facts and statistics supported by the
        evidence_source attached to the rule." A rule with none has nothing to
        check a statistic against."""
        docs, _report = parsed
        for rule in [d for d in docs if d["kind"] == "rule"]:
            assert rule.get("evidence_source"), rule["rule_label"]

    def test_only_the_ink_rules_are_confidential(self, parsed):
        """C 16 names one source: "Original HP Ink Portfolio is HP Confidential
        / Internal-Channel Partner use only.\""""
        docs, _report = parsed
        confidential = {d["family"] for d in docs
                        if d["kind"] == "rule" and d.get("confidential")}
        assert confidential == {"INK"}

    def test_order_is_continuous_within_a_family(self, parsed):
        """PRINT now spans two tables. Counting `order` per table restarted it
        at 1 for PRINT 04, which made the rulebook's own document-order
        tie-break ambiguous for the family the revision expanded."""
        docs, _report = parsed
        for family in ("PRINT", "SCAN"):
            orders = [d["order"] for d in docs
                      if d["kind"] == "rule" and d["family"] == family]
            assert len(set(orders)) == len(orders), family
            assert sorted(orders) == list(range(1, len(orders) + 1)), family

    def test_every_rule_carries_the_twelve_field_record(self, parsed):
        """C 11: "Every runtime offering must carry offering_id, name,
        business_unit, what_it_enables, qualifying_conditions,
        integration_routes, disqualifiers, proof_ids, market_availability and
        evidence_source, plus owner and version for governance.\""""
        docs, _report = parsed
        required = {"offering_id", "name", "business_unit", "what_it_enables",
                    "qualifying_conditions", "integration_routes",
                    "disqualifiers", "proof_ids", "market_availability",
                    "evidence_source", "owner"}
        for rule in [d for d in docs if d["kind"] == "rule"]:
            assert set(rule["structured"]) >= required, rule["rule_label"]
            assert rule["structured"]["offering_id"] == rule["_id"]

    def test_no_family_was_dropped_for_being_unknown(self, parsed):
        """A bare `continue` on an unrecognised family once meant a load could
        report success having stored six fewer rules than the document."""
        _docs, report = parsed
        assert report["unknown_families"] == []

    def test_the_shipped_flags_still_line_up_with_the_document(self, parsed):
        """Two disagreements are known and deliberate (rules 1 and 18). More
        than that means the document moved and the table needs revisiting."""
        _docs, report = parsed
        assert len(report["flag_disagreements"]) <= 2
