"""Match an account's verified evidence to the HP 220 Account Rulebook.

`scripts/load_rulebook.py` loads the corpus; this chooses from it. Nothing here
writes prose, and nothing here calls a model: the rulebook already states what
may be said, so the only judgement left is which rule the account's own evidence
earns. Python owns that, the way it owns every other gate in this codebase.

## The rulebook's own instructions, and where each one lives

    C 01  "The account need must come from verified account research. HP
           materials cannot prove that the account has a problem."
          -> `candidates`. Every rule must be fired by the ACCOUNT's own
             evidence, on its own terms. A rule can never pull itself in, and
             HP material is never evidence of anything.

             `route` reports which of the eight opportunity types the account
             raises, and names the type a fired rule belongs to. It is NOT a
             gate. It was one, and it threw away real matches: WOLF 09 matches
             on "kaspersky" and "symantec endpoint protection", both of which
             the account runs, while the Security routing row had drawn thinner
             wording the account does not use - so the family never opened and
             the rule was never consulted. Both vocabularies come from the same
             non-deterministic derivation, so which is better is luck, and
             gating the good one behind the poor one is not a rule the document
             asks for. It calls the routing table a path: "Choose the
             opportunity type ... Go to these rules."

    C 06  "Give one main recommendation. Add another product or service only
           when separate verified evidence supports it."
          -> `select`. One primary; a secondary is admitted only when the
             evidence that fired it is DISJOINT from the primary's. That is a
             literal reading of "separate verified evidence" and it is testable,
             which "related enough to be worth adding" would not be.

    C 07  "If no rule matches, or a required condition written in the rule
           cannot be verified from account evidence, leave out the
           recommendation or label the missing condition clearly."
          -> `check_conditions`. Both branches, never a silent pass. A condition
             the loader can test against account evidence and which fails drops
             the rule. A condition nothing in the uploads could confirm is
             returned as `unverified` for the card to show.

    C 02  "Use only the HP facts written in the matched rule ... the engine must
           not reopen the original HP files."
          -> `facts_for`. Facts come from the rule and nowhere else. This module
             never reads `hp_product_knowledge`.

## Returning nothing is a correct answer

Same principle the case-study matcher runs on, and the rulebook says it in its
own words at C 07: "Do not force a match." An account whose evidence raises no
opportunity type gets no rules, and a family whose conditions cannot be met gets
none of its own. On a typical account most of the eight types will not fire.
"""

import logging
import re

from app.services.hp.product_rules import _is_excluded, token_present

logger = logging.getLogger(__name__)

COLLECTION = "hp_rulebook"
VERSION_DOC_ID = "__knowledge_version__"

# How many rules one opportunity type may contribute. A family like CARE holds
# twenty rules and several will fire on the same ticket-volume sentence; a card
# carrying all of them is a catalogue, not a recommendation.
MAX_RULES_PER_FAMILY = 3


def knowledge_version(db) -> str:
    """The loaded rulebook's version, for a feature's cache fingerprint.

    Returns "" when the rulebook has never been loaded, which is stable: a
    platform with no rulebook should not rebuild every widget on every run.
    """
    try:
        doc = db[COLLECTION].find_one({"_id": VERSION_DOC_ID}) or {}
    except Exception:
        logger.exception("rulebook: could not read the knowledge version")
        return ""
    return str(doc.get("knowledge_version") or "")


def load(db) -> dict:
    """Everything the matcher needs, in one read.

    The whole rulebook is 166 documents, so reading it whole costs nothing and
    saves the caller from issuing a query per family per card.
    """
    try:
        docs = list(db[COLLECTION].find({"_id": {"$ne": VERSION_DOC_ID}}))
    except Exception:
        logger.exception("rulebook: load failed")
        return {"rules": [], "routing": [], "matrices": {}, "guardrails": [],
                "country_lists": {}}

    matrices: dict = {}
    for d in docs:
        if d.get("kind") == "matrix":
            matrices.setdefault(d["matrix"], []).append(d)

    return {
        "rules": sorted([d for d in docs if d.get("kind") == "rule"],
                        key=lambda r: (r.get("part") or "", r.get("order") or 0)),
        "routing": sorted([d for d in docs if d.get("kind") == "routing"],
                          key=lambda r: r.get("order") or 0),
        "matrices": matrices,
        "guardrails": [d for d in docs if d.get("kind") == "guardrail"],
        "country_lists": {d["restriction"]: d
                          for d in docs if d.get("kind") == "country_list"},
    }


# ==============================================================================
# C 01 - the account's own evidence decides what is even considered
# ==============================================================================

def _evidence_text(item) -> str:
    if isinstance(item, dict):
        return " ".join(str(item.get(k) or "") for k in ("text", "statement", "quote"))
    return str(item or "")


def _match_terms(row: dict) -> list:
    """Everything a rule or routing row can be recognised by.

    Two sets, built for different jobs and used together:

    `signal_tokens` are anchored in the rule's own wording. Precise, and on
    their own almost useless - measured against a real account they fired
    nothing at all, because the rulebook describes business problems ("employee
    technology friction") and an account's exports list vendors and job titles
    ("ManageEngine", "Engineering Manager"). No matcher bridges that; only
    knowledge does.

    `observable_terms` are that knowledge, derived once at load time: what the
    account's own files would actually say if the rule's signal were true. They
    are what makes a rule reachable.
    """
    return list(row.get("signal_tokens") or []) +         list(row.get("observable_terms") or [])


def _fired_by(row_or_tokens, evidence) -> tuple:
    """(evidence indices, the distinct terms that matched).

    Indices rather than the items themselves, because C 06 needs to compare two
    rules' evidence as sets and an evidence dict is not hashable.

    The matched terms come back too, because how many DIFFERENT terms recognised
    a rule turns out to matter more than how many cells did. See `_rank`.
    """
    tokens = (_match_terms(row_or_tokens) if isinstance(row_or_tokens, dict)
              else list(row_or_tokens or []))
    hits, matched = [], set()
    for i, item in enumerate(evidence or []):
        text = _evidence_text(item)
        if not text or _is_excluded(text):
            continue
        fired = [t for t in tokens if token_present(t, text)]
        if fired:
            hits.append(i)
            matched.update(fired)
    return hits, matched


def route(book: dict, evidence) -> list:
    """The opportunity types this account's evidence raises, in document order.

    Each is `{opportunity_type, families, evidence_indices}`. An account that
    raises none gets an empty list, and that is the end of the matter - no rule
    is considered, because C 01 says HP material cannot establish the need.
    """
    fired = []
    for row in book.get("routing") or []:
        hits, matched = _fired_by(row, evidence)
        if hits:
            fired.append({
                "opportunity_type": row["opportunity_type"],
                "families": list(row.get("families") or []),
                "evidence_indices": hits,
                "matched_terms": sorted(matched),
            })
    return fired


# ==============================================================================
# C 07 - conditions, and the two things that can happen to one
# ==============================================================================

TESTABLE = frozenset({"country", "management_environment", "os"})


def check_conditions(rule: dict, evidence, account_country: str = "") -> tuple:
    """(satisfied, unmet, unverified).

    `unmet` is a testable condition the account contradicts - the rule is
    dropped. `unverified` is a condition nothing here can test; the rule
    survives and the card says so, which is C 07's second branch.

    Only country conditions are actually decidable today, and only when the
    rule names a country the account is not in. Everything else is labelled.
    That asymmetry is deliberate: a condition wrongly judged unmet deletes a
    valid recommendation silently, while one wrongly labelled merely asks a
    seller to check. The first failure is invisible, so the bar for it is high.
    """
    unmet, unverified = [], []
    country = " ".join(str(account_country or "").split()).lower()
    haystack = " ".join(_evidence_text(i) for i in (evidence or []))

    for condition in rule.get("conditions") or []:
        kind = condition.get("condition_type")
        text = condition.get("text") or ""

        if kind not in TESTABLE:
            unverified.append(condition)
            continue

        if kind == "country":
            named = _countries_named(text)
            if not named or not country:
                unverified.append(condition)
            elif not any(c in country for c in named):
                unmet.append(condition)
            continue

        # Management environment and operating system. A condition is satisfied
        # when the account's own uploads name the same thing. Not finding it is
        # NOT a contradiction - an export simply may not list it - so the miss
        # is labelled rather than counted against the rule.
        named = [t for t in (_ENV_TERMS if kind == "management_environment"
                             else _OS_TERMS)
                 if token_present(t, text)]
        if named and any(token_present(t, haystack) for t in named):
            continue
        unverified.append(condition)

    return (not unmet), unmet, unverified


# The environments and systems a condition can name, as a closed vocabulary.
# Closed because a condition is only testable when we know what to look for;
# anything outside these is labelled for a seller to check, which is the safe
# direction.
_ENV_TERMS = ("intune", "entra", "autopilot", "sccm", "vpro", "azure",
              "active directory", "on-premises", "cloud portal", "tenancy")
_OS_TERMS = ("windows", "macos", "linux", "android", "ios", "chromeos")

# Countries a condition can name. Short and closed on purpose: the only country
# conditions in the rulebook today are HP IQ's "United States and in English"
# launch scope, and inventing a general country parser for one rule would be
# more code than the document supports.
_COUNTRY_PHRASES = {
    "united states": ("united states", "usa", "u.s."),
    "english": ("english",),
}


def _countries_named(text: str) -> list:
    low = " ".join(str(text or "").split()).lower()
    out = []
    for canonical, forms in _COUNTRY_PHRASES.items():
        if any(f in low for f in forms):
            out.append(canonical)
    # "English" is a language condition, not a market the account can be in.
    return [c for c in out if c != "english"]


# ==============================================================================
# Candidates and selection
# ==============================================================================

# A rule whose own text says the rulebook holds nothing about the offering.
#
# Seven rules read this way - "This rulebook contains no deliverables,
# duration, response time, or service-level details for it", "It provides no
# additional capability description". The offering is real and the seller may
# name it, but there is nothing to say about it, so leading a recommendation
# with one puts an empty card at the top of the page. WXP 12 did exactly that.
#
# They are treated like `modifier_only`: worth knowing alongside a
# recommendation, never the recommendation. Read from the stored facts rather
# than flagged at load time, so correcting this costs no reload.
_NO_DETAIL_RE = re.compile(
    r"\b(contains? no|provides? no|does not contain|does not provide|does not map)\b", re.I)


def _catalogue_only(rule: dict) -> bool:
    return bool(_NO_DETAIL_RE.search(" ".join(rule.get("allowed_facts") or [])))


# The datasets that can carry a verified account need. Deliberately the same
# ones the Opportunity Map reasons over - a rule must be earned by evidence a
# seller could already see on a card, not by a dataset nothing else reads.
#
# `prospect_contacts` is absent on purpose. A contact record carries a person's
# LinkedIn skills, and a skill is an attribute of that person rather than of the
# estate: matching on one recommended TROY secure cheque printing to an account
# because a contact listed "payment processing" among their skills. C 01 asks
# that the NEED come from account research, and what an individual knows how to
# do is not the company having that requirement.
EVIDENCE_DATASETS = (
    "firmographics", "technographics", "job_openings", "intent_topics",
    "news_events", "google_news", "webstack", "technology_detections",
)

# Fields that carry no account need, however long their value is. Ids, stamps
# and URLs are most of a row by count and none of it by meaning; feeding them
# to the matcher is noise that can only produce accidental hits.
_NOISE_FIELD = re.compile(
    r"(^|_)(id|uuid|url|link|domain|date|stamp|seen_at|processed_at|"
    r"created|updated|score|count|currency|salary|lat|lon|zip|postal)(_|$)", re.I)
_NOISE_VALUE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-|^\d{4}-\d{2}-\d{2}t|^https?://|^[\d.,%\s-]+$", re.I)


def _is_meaningful(field: str, text: str) -> bool:
    if len(text) < 4 or text.startswith(("{", "[")):
        return False
    if _NOISE_FIELD.search(str(field or "")):
        return False
    return not _NOISE_VALUE.match(text)


def account_evidence(account_id: str) -> list:
    """The cells of the account's uploads that could carry a verified need.

    Lives here rather than in the verification script that first needed it:
    every feature matching against the rulebook must reason over the same
    evidence, or two features give a seller different answers about the same
    account and neither is wrong. The Objection Playbook reads three datasets
    for its own grounding, and building the match corpus from those alone left
    it 39 cells to work with against this account's 3,000.
    """
    from app.services.extractors.datasets import read_dataset_records

    evidence = []
    for dataset in EVIDENCE_DATASETS:
        try:
            records = read_dataset_records(account_id, dataset)
        except Exception:
            logger.debug("rulebook: %s unavailable for %s", dataset, account_id)
            continue
        for record in records or []:
            for field, value in (record or {}).items():
                text = " ".join(str(value or "").split())
                if _is_meaningful(field, text):
                    evidence.append({"text": text, "dataset": dataset,
                                     "field": field})
    return evidence


def account_country(account_id: str) -> str:
    """The account's country, for the market and superlative gates."""
    from app.services.extractors.datasets import read_dataset_records

    try:
        rows = read_dataset_records(account_id, "firmographics") or []
    except Exception:
        return ""
    for row in rows:
        for key in ("Country Name", "Country", "Hq Location", "Headquarters"):
            value = " ".join(str((row or {}).get(key) or "").split())
            if value:
                return value
    return ""


# The HP line each Part B family speaks for, and the inverse. Rulebook taxonomy,
# so it lives with the rulebook rather than in whichever feature needed it
# first - the Technographic Map reads it to name a vendor card's offering, and
# the Objection Playbook to find the rules that may answer an objection.
#
# HARDWARE is absent on purpose: Part A chooses a specific machine, and the
# lines here are product families. An HP line absent from the inverse map draws
# no offering, which is the safe direction - the caller keeps the broad line it
# already had rather than being given a rule the rulebook never connected to it.
RULEBOOK_FAMILY_TO_HP_LINE = {
    "WOLF": "HP Wolf Security",
    "POLY": "Poly Collaboration",
    "PRINT": "HP Enterprise Print / MPS",
    "SCAN": "HP Enterprise Print / MPS",
    "WXP": "HP Workforce Experience Platform",
    "CARE": "HP Care Pack Services",
    "LIFE": "HP Lifecycle & Sustainability Services",
    "DEPLOY": "HP Deployment & Configuration Services",
    "IQ": "HP IQ for Enterprise",
    "INK": "Original HP Ink",
}


HP_LINE_TO_RULEBOOK_FAMILIES = {
    "hp wolf security": ("WOLF",),
    "poly collaboration": ("POLY",),
    "hp enterprise print / mps": ("PRINT", "SCAN"),
    "original hp ink": ("INK",),
    "hp anyware / daas": ("WXP", "DEPLOY"),
    "hp workforce experience platform": ("WXP",),
}


# Vendors and platforms so widely deployed that finding one in an account's
# files says nothing about that account. The loader already refuses a BARE one
# ("microsoft"); these are the qualified spellings that slip past it because
# they are two words long - "sap erp", "microsoft teams", "google workspace".
_UBIQUITOUS_VENDORS = frozenset((
    "microsoft", "google", "apple", "adobe", "oracle", "sap", "amazon", "aws",
    "azure", "cisco", "ibm", "windows", "linux", "android", "ios", "macos",
    "chrome", "office", "teams", "zoom", "slack", "outlook", "excel", "word",
    "sharepoint", "onedrive", "gmail", "workspace", "salesforce", "jira",
    "confluence",
))

# Product-category nouns that add no discriminating power to a vendor name.
# "sap erp" is "sap"; "salesforce health cloud" is not "salesforce", because
# "health" narrows it to something an account might genuinely not have.
_GENERIC_QUALIFIERS = frozenset((
    "erp", "crm", "cloud", "suite", "platform", "enterprise", "software",
    "system", "systems", "solution", "solutions", "services", "service",
    "tools", "tool", "application", "applications", "app", "apps",
    "financials", "server", "servers", "online", "premium", "pro", "plus",
    "standard", "edition",
))


def indicative_term(term: str) -> bool:
    """Whether a term merely indicates a candidate rather than qualifying it.

    A term qualifies a rule when finding it in an account's files is evidence
    that the account has the need the rule addresses. A term is only INDICATIVE
    when it describes what the offering would plug into, or names a platform
    every enterprise runs.

    The distinction is not pedantry. PRINT 21 recommends TROY secure cheque
    printing on a signal the rulebook words as "a VERIFIED secure check-printing
    or MICR requirement", and it fired on "sap erp" - a term that describes what
    TROY integrates with. Almost every large account runs an ERP, so on that
    evidence the rule would be offered to almost every large account, none of
    whom were shown to print cheques.
    """
    words = str(term or "").split()
    if not words:
        return True
    return (any(w in _UBIQUITOUS_VENDORS for w in words)
            and all(w in _UBIQUITOUS_VENDORS or w in _GENERIC_QUALIFIERS
                    for w in words))


def split_terms(rule: dict, matched) -> tuple:
    """(qualifying, indicative) for the terms one rule matched on.

    A term is only INDICATIVE - it points at a rule without earning it - in two
    cases the rulebook itself describes.

    The first is a term every enterprise would match; see `indicative_term`.

    The second is a rule the loader flagged `routing_only`, meaning its own
    system action says the signal routes rather than qualifies. PRINT 25 is the
    case that prompted this: its signal text enumerates the verticals it covers,
    so "financial services" is part of the rule's OWN wording, and its action
    reads "Treat industry as a routing signal only ... do not invent a vertical
    app or capability from the industry name alone." Such a rule needs an
    observable term - something the account would say if the need were real -
    and not merely its own words echoed back.

    Every other rule may be earned by its own wording appearing in the account's
    files, because an account writing "high ticket volume" in its own documents
    IS evidence of the need. That is the account speaking, not the rule
    vouching for itself, and C 01 asks only that the need come from the account.
    """
    observable = set(rule.get("observable_terms") or [])
    # With no observable vocabulary derived, requiring one would delete the
    # rule rather than gate it.
    needs_observable = bool(rule.get("routing_only")) and bool(observable)

    qualifying = []
    for term in matched:
        if indicative_term(term):
            continue
        if needs_observable and term not in observable:
            continue
        qualifying.append(term)
    return qualifying, [t for t in matched if t not in qualifying]


def _rank(match: dict) -> tuple:
    """How well a rule is earned, best first.

    Distinct terms before raw hit count, and that order is the whole point.
    Counting cells rewards whichever rule owns the broadest term: on a real
    account "microsoft" appeared in 40 technographics cells and carried a rule
    about an onboarding service to the top of the list, over rules recognised
    by three specific terms each. A rule that three different things point at
    is better earned than one the same word points at forty times.
    """
    return (-len(match.get("qualifying_terms") or match["matched_terms"]),
            -len(match["matched_terms"]),
            -len(match["evidence_indices"]),
            match["rule"].get("order") or 0)


def candidates(book: dict, evidence, routes=None, account_country: str = "",
               drops: list | None = None) -> list:
    """Rules this account's evidence earns, best first.

    Only families a routing type raised are considered (C 01). Within a family
    a rule must itself be fired by the account's evidence - the routing type
    opens the door, it does not admit every rule behind it.
    """
    routes = route(book, evidence) if routes is None else routes

    # The rulebook's own document order breaks ties between families. Sorting
    # on the family NAME instead was alphabetical and therefore arbitrary - it
    # put a Wolf Security rule ahead of a workforce one purely because "WOLF"
    # sorts before "WXP", which is not a reason a seller would accept.
    #
    # A family whose routing row also fired ranks ahead of one that reached us
    # only through its own rules: the account raised the topic in two
    # independent ways rather than one.
    # Which opportunity type each family belongs to, from the document's own
    # routing table. Built for every family, not only the ones that routed,
    # because the cap below is keyed on the type and a family that reached us
    # through its own rules still belongs to one.
    family_type = {}
    for row in book.get("routing") or []:
        for family in row.get("families") or []:
            family_type.setdefault(family, row["opportunity_type"])

    family_rank, position = {}, 0
    for r in routes:
        for family in r["families"]:
            family_rank.setdefault(family, position)
            position += 1
    for row in book.get("routing") or []:
        for family in row.get("families") or []:
            family_rank.setdefault(family, position + (row.get("order") or 0))

    # HP IQ is a United States, English-only launch (IQ 01 with G 13 and
    # G 14), and IQ 01 is the gate for the whole family: "Verified enterprise
    # AI adoption plus an employee workflow covered by IQ 02 to IQ 11." Where
    # the market fails, no IQ rule is reachable - so none is offered, rather
    # than each one being tested and silently dropped further down.
    blocked_families = set()
    if iq_availability(book, account_country)["available"] is False:
        blocked_families.add("IQ")

    # WOLF 01: the offering is chosen from the matrix, not assumed. An estate
    # with no HP client hardware cannot take the two HP-only offerings.
    hp_clients = has_hp_client_hardware(evidence)

    by_family: dict = {}
    for rule in book.get("rules") or []:
        family = rule.get("family")
        if family in blocked_families:
            continue
        hits, matched = _fired_by(rule, evidence)
        if not hits:
            continue

        # C 07, and the reason it exists: "leave out the recommendation ... Do
        # not force a match." A rule earned only by terms that describe what the
        # offering plugs into, or by its own wording, has not been shown to
        # apply to this account.
        qualifying, indicative = split_terms(rule, sorted(matched))
        if not qualifying:
            by_family.setdefault(family, {"dropped": []})["dropped"].append(
                {"rule_label": rule["rule_label"],
                 "unmet": ["matched only on %s, which indicates a candidate "
                           "rather than evidence of the need this rule "
                           "addresses" % ", ".join(repr(t) for t in indicative)]})
            continue

        if family == "WOLF" and not wolf_offering_allowed(
                book, rule.get("offering"), hp_clients):
            by_family.setdefault(family, {"dropped": []})["dropped"].append(
                {"rule_label": rule["rule_label"],
                 "unmet": ["%s needs HP client hardware, and none is detected "
                           "in this account's technology export"
                           % rule.get("offering")]})
            continue

        satisfied, unmet, unverified = check_conditions(
            rule, evidence, account_country)
        if not satisfied:
            # C 07, first branch. Recorded rather than dropped silently, so a
            # caller can report why a family produced nothing.
            by_family.setdefault(family, {"dropped": []})["dropped"].append(
                {"rule_label": rule["rule_label"],
                 "unmet": [c["text"] for c in unmet]})
            continue

        by_family.setdefault(family, {"dropped": []}).setdefault("kept", []).append({
            "rule": rule,
            "rule_label": rule["rule_label"],
            "family": family,
            "offering": rule.get("offering"),
            "evidence_indices": hits,
            "opportunity_type": family_type.get(family, family),
            "matched_terms": sorted(matched),
            # Kept apart so a caller can show what actually earned the rule
            # rather than what merely pointed at it.
            "qualifying_terms": qualifying,
            "indicative_terms": indicative,
            "unverified_conditions": [c["text"] for c in unverified],
            # A rule that may never stand alone (C 06). Kept as a candidate
            # because it still qualifies a recommendation, but `select` will
            # not promote one to primary.
            "modifier_only": bool(rule.get("modifier_only")),
            "routing_only": bool(rule.get("routing_only")),
            "catalogue_only": _catalogue_only(rule),
        })

    # Everything refused, for a caller that has to explain a thin page. The
    # refusals were only ever logged, so a feature showing one card could not
    # say whether one rule fired or five - and "four more fired and were
    # refused, here is why" is the answer a seller actually needs.
    if drops is not None:
        for family, bucket in by_family.items():
            for dropped in bucket.get("dropped") or []:
                drops.append({**dropped, "family": family})

    out = []
    for family, bucket in by_family.items():
        kept = bucket.get("kept") or []
        # More distinct evidence items behind a rule is a better-earned rule.
        # The rulebook's own order breaks ties, so a rerun on unchanged data
        # returns the same rule.
        kept.sort(key=_rank)

        # The cap limits how many RECOMMENDATIONS one family may offer, so a
        # rule that can never be one must not spend a slot. Part A's eighteen
        # rules all sit in the family "HARDWARE", and a modifier ranked third
        # pushed out rule 1 - the EliteBook that HP's own "AI hiring" signal had
        # just earned - before `select` ever saw it. Modifiers are carried
        # uncapped: they qualify other recommendations rather than competing
        # with them, and `select` needs them for the branch where nothing
        # stands alone.
        standalone = [m for m in kept if not (m["modifier_only"]
                                              or m["routing_only"]
                                              or m["catalogue_only"])]
        qualifiers = [m for m in kept if m not in standalone]
        out.extend(standalone[:MAX_RULES_PER_FAMILY] + qualifiers)
        if not kept and bucket.get("dropped"):
            logger.info("rulebook: %s produced no rule; %d dropped on conditions",
                        family, len(bucket["dropped"]))

    out.sort(key=lambda m: (-len(m.get("qualifying_terms") or ()),
                            -len(m["matched_terms"]),
                            -len(m["evidence_indices"]),
                            family_rank.get(m["family"], len(routes)),
                            m["rule"].get("order") or 0))
    return out


def _type_of(match: dict) -> str:
    """The opportunity type a match belongs to, falling back to its family."""
    return match.get("opportunity_type") or match.get("family") or ""


def select(matches: list) -> dict:
    """C 06: one main recommendation, plus anything separate evidence supports.

    `{primary, secondary, withheld}`. A secondary is admitted only when the
    evidence that fired it does not overlap the primary's at all. Two rules
    reading the same sentence are one recommendation with two labels, and
    presenting them as two is exactly what C 06 forbids.
    """
    standalone = [m for m in matches
                  if not (m["modifier_only"] or m["routing_only"]
                          or m["catalogue_only"])]
    if not standalone:
        # Same keys as the normal path. An earlier version omitted "modifiers"
        # here, so a caller that iterated it crashed on exactly the accounts
        # where nothing stood alone - the case this branch exists for.
        return {"primary": None, "secondary": [],
                "modifiers": list(matches),
                "withheld": [],
                # Every rule that fired is a qualifier. Saying so is more useful
                # than an empty result, because it means the evidence IS on
                # topic and only the standalone rule is missing.
                "reason": ("every rule that fired either qualifies another "
                           "recommendation or is a catalogue entry the rulebook "
                           "says nothing about" if matches else "no rule fired")}

    primary = standalone[0]
    claimed = set(primary["evidence_indices"])
    # Keyed on the OPPORTUNITY TYPE, not the family. The revision made the
    # difference matter: PRINT, SCAN and INK are three families under the one
    # "Print and scan" type, so a family-keyed cap would have let all three
    # onto a page labelled with the same opportunity - the catalogue the cap
    # exists to prevent.
    spoken_for = {_type_of(primary)}
    secondary, withheld = [], []

    for match in standalone[1:]:
        overlap = claimed & set(match["evidence_indices"])
        if overlap:
            withheld.append({**match,
                             "withheld_because": "the same evidence already "
                                                 "supports %s" % primary["rule_label"]})
            continue
        # At most one play per opportunity type. C 06 says "Give one main
        # recommendation. Add ANOTHER product or service only when separate
        # verified evidence supports it" - singular, and a page carrying four
        # Care Pack rules is a catalogue rather than a recommendation. The
        # opportunity types are the axes the rulebook itself defines, so one
        # per axis is the reading that matches the document.
        # The per-type cap is a Part B rule. Part B's nine families ARE the
        # opportunity types, so four Care Pack rules on one page is a
        # catalogue. Part A's eighteen rules all sit in one family called
        # HARDWARE while naming eighteen different products, so applying it
        # there allowed exactly one hardware recommendation ever - it withheld
        # an EliteBook fleet play because a desktop play "already speaks for
        # this opportunity type". For Part A the disjoint-evidence test above
        # is the whole of C 06, which is what the rule literally says.
        if match["rule"].get("part") != "A" and _type_of(match) in spoken_for:
            withheld.append({**match,
                             "withheld_because": "%s already speaks for this "
                                                 "opportunity type"
                                                 % next(m["rule_label"] for m in
                                                        [primary, *secondary]
                                                        if _type_of(m) == _type_of(match))})
            continue
        secondary.append(match)
        spoken_for.add(_type_of(match))
        claimed |= set(match["evidence_indices"])

    modifiers = [m for m in matches if m["modifier_only"] or m["routing_only"]
                 or m["catalogue_only"]]
    return {"primary": primary, "secondary": secondary,
            "modifiers": modifiers, "withheld": withheld, "reason": None}


# ==============================================================================
# C 02 - the facts, and only the rulebook's facts
# ==============================================================================

# Sentences that instruct whoever writes the recommendation, rather than
# stating something a reader has to know. "Mention only the integration that
# matches the account evidence" reads as a caveat about THIS account when it is
# shown as an unverified condition, and it is nothing of the sort - it is HP
# telling the writer to be selective.
#
# They stay in `allowed_facts`, because that is what the writer reads and the
# instruction is useful there. They are kept out of `unverified_conditions`,
# which is what the seller reads.
#
# Matched on the opening verb: a sentence beginning "Recommend", "Use",
# "Mention" is addressed to the engine, while "Version 1.0 begins in the United
# States" and "This rulebook does not contain a capability-to-tier mapping"
# open on a subject and describe a limit that does reach the reader.
_ENGINE_DIRECTED = (
    "recommend", "use ", "choose", "mention", "keep ", "treat ", "apply ",
    "select", "present ", "name ", "offer ", "position ", "pair ", "add ")


def _reader_facing(text: str) -> bool:
    low = " ".join(str(text or "").split()).lower()
    return bool(low) and not low.startswith(_ENGINE_DIRECTED)


# A figure a seller could repeat to a customer. C 16 names the kinds that
# matter: "Claims such as savings, page yield, environmental impact or
# comparative performance may be used only with the corresponding source
# footnotes and conditions."
_QUANTIFIED_RE = re.compile(r"\d[\d,.]*\s*(%|percent|pages|ppm|per cent)|\b\d{2,}\b", re.I)


def _confidential_fact_allowed(text: str, conditions: list) -> bool:
    """Whether a fact from a confidential source may be stated as written.

    C 16 governs the Original HP Ink Portfolio, which is "HP Confidential /
    Internal-Channel Partner use only". It does not forbid using the rules - it
    forbids exposing internal labels and unsupported quantified claims. So a
    sentence carrying no figure passes untouched, and one carrying a figure
    passes only when the rule also supplies the condition that qualifies it.
    """
    if not _QUANTIFIED_RE.search(str(text or "")):
        return True
    return bool(conditions)


def facts_for(match: dict) -> dict:
    """What a recommendation built on this rule may state.

    Everything comes from the rule's own row. `hp_product_knowledge` - the
    corpus extracted from HP's decks - is deliberately not consulted: C 02 says
    the engine must not reopen the original HP files, and the deck corpus is
    exactly those files.
    """
    rule = match["rule"]
    conditions = [c.get("text") for c in (rule.get("conditions") or [])
                  if isinstance(c, dict) and c.get("text")]

    facts = list(rule.get("allowed_facts") or [])
    withheld = []
    if rule.get("confidential"):
        kept = []
        for fact in facts:
            if _confidential_fact_allowed(fact, conditions):
                kept.append(fact)
            else:
                withheld.append(fact)
        facts = kept

    return {
        "rule_label": rule["rule_label"],
        "part": rule.get("part"),
        "family": rule.get("family"),
        "offering": rule.get("offering"),
        "allowed_facts": facts,
        # C 16, made visible rather than silent: a seller should be able to see
        # that a figure exists and was held back for want of its footnote.
        "withheld_for_confidentiality": withheld,
        "confidential": bool(rule.get("confidential")),
        "evidence_source": rule.get("evidence_source"),
        "prohibitions": list(rule.get("prohibitions") or []),
        "system_action": rule.get("system_action"),
        "unverified_conditions": [c for c in (match.get("unverified_conditions") or [])
                                  if _reader_facing(c)],
        "fact_source": "rulebook",
        "provenance": rule.get("material"),
    }


# ==============================================================================
# The two family gates the rulebook spells out separately
# ==============================================================================

# HP client hardware, as an account's technology export would name it. Used
# only to answer the Wolf matrix's device-support column.
_HP_CLIENT_HARDWARE = (
    "hp elitebook", "hp probook", "hp elitedesk", "hp prodesk", "hp zbook",
    "hp elitestudio", "hp prostudio", "hp elite pc", "hp pro pc",
    "hp workstation", "hp z workstation", "hp dragonfly", "hp omnibook",
)


def has_hp_client_hardware(evidence) -> bool:
    """Whether the account's own evidence shows HP client hardware.

    Not an inference from the absence of a signal: a technographics export that
    names no HP device is what "no HP client hardware detected" means here, and
    it is the same reading the Technographic Map already publishes as
    whitespace.
    """
    blob = " ".join(_evidence_text(i) for i in (evidence or [])).lower()
    return any(name in blob for name in _HP_CLIENT_HARDWARE)


def wolf_offering_allowed(book: dict, offering: str, has_hp_clients: bool) -> bool:
    """Whether this estate can take the named Wolf offering.

    The matrix's device-support column is the gate. "Eligible HP PCs only" and
    "Select HP commercial PCs only" mean exactly that, and G 17 forbids
    borrowing another offering's conditions to get around it.

    An offering the matrix does not list is allowed: the rules carry offerings
    the four-row matrix does not name, and refusing those would suppress rules
    the document plainly intends to be usable.
    """
    if has_hp_clients:
        return True
    wanted = " ".join(str(offering or "").split()).lower()

    # Longest name first. "Wolf Pro Security" is a substring of "Wolf Pro
    # Security Edition", so matching in matrix order answered the Edition's
    # question with the base product's row - and the Edition is the one
    # restricted to select HP commercial PCs.
    rows = sorted((book.get("matrices") or {}).get("wolf") or [],
                  key=lambda r: -len(str(r.get("offering") or "")))
    for row in rows:
        if " ".join(str(row.get("offering") or "").split()).lower() not in wanted:
            continue
        support = " ".join(str(v) for k, v in (row.get("columns") or {}).items()
                           if "device" in str(k).lower()).lower()
        return "hp pcs only" not in support and "hp commercial pcs only" not in support
    return True


def wolf_offering(book: dict, evidence, has_hp_clients: bool) -> dict | None:
    """The one Wolf Security offering this estate can actually take.

    WOLF 01 is routing-only in the document's own words: "Choose the offering
    using the segment, device support, licence, management model, and
    capabilities written in WOLF 02 to WOLF 20 and the selection matrix below.
    Do not recommend a generic Wolf Security bundle."

    The matrix's device-support column is the gate. Two of the four offerings
    are for eligible or select HP commercial PCs only, so an estate with no HP
    client hardware can take neither - and G 17 forbids mixing conditions
    between them, so exactly one row is returned rather than a blend.
    """
    rows = (book.get("matrices") or {}).get("wolf") or []
    eligible = []
    for row in rows:
        columns = row.get("columns") or {}
        support = " ".join(str(v) for k, v in columns.items()
                           if "device" in str(k).lower()).lower()
        hp_only = "hp pcs only" in support or "hp commercial pcs only" in support
        if hp_only and not has_hp_clients:
            continue
        eligible.append(row)

    if not eligible:
        return None
    # Document order is HP's own, least to most capable; the narrowest offering
    # the estate can take is the honest default.
    return sorted(eligible, key=lambda r: r.get("order") or 0)[0]


def iq_availability(book: dict, account_country: str) -> dict:
    """Whether HP IQ can be offered in this account's market at all.

    IQ 01 and guardrail G 14 put Version 1.0 in the United States, in English.
    That is not a condition a seller can go and verify - it is unsatisfiable
    anywhere else - so it is reported as a market block with its reason rather
    than left to make twelve rules quietly never fire.
    """
    country = " ".join(str(account_country or "").split()).lower()
    rows = (book.get("matrices") or {}).get("iq") or []
    if not country:
        return {"available": None, "reason": "the account's country is not known",
                "compatibility": rows}
    if "united states" in country or country in ("us", "usa"):
        return {"available": True, "reason": None, "compatibility": rows}
    return {
        "available": False,
        "reason": ("HP IQ for Enterprise Version 1.0 launches in the United "
                   "States and in English; this account is in %s"
                   % account_country),
        "compatibility": rows,
    }


# ==============================================================================
# Guardrails
# ==============================================================================

def blocked_countries(book: dict, restriction: str) -> set:
    """The document's own country list for a restriction, folded for matching.

    `services/hp/guardrails.py` holds the runtime constants - they are imported
    at module scope in two features and must not become a database read - so
    this exists to check those constants against the document rather than to
    replace them. `scripts/verify_rulebook.py` does that comparison.
    """
    row = (book.get("country_lists") or {}).get(restriction) or {}
    return set(row.get("countries_folded") or [])


def guardrails_for(book: dict, scope: str = "") -> list:
    rows = book.get("guardrails") or []
    if scope:
        rows = [r for r in rows if r.get("scope") == scope]
    return sorted(rows, key=lambda r: (r.get("scope") or "", r.get("order") or 0))
