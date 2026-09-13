"""Factual grounding for the Message Evaluator - which source may establish what.

Four sources feed an evaluation, and each has a defined, non-overlapping
authority. The whole point of separating them is that a claim verified against
the wrong one is not verified at all:

    submitted draft   may establish  where a phrase sits in the text
                      never          anything factual - a claim is not true
                                     because the seller wrote it

    account corpus    may establish  facts about this account
                      never          HP product capability

    HP fact corpus    may establish  HP product capability
                      never          any fact about the account

    persona context   may establish  the contact's role, department, seniority
                      never          what that person thinks, wants or has said

The two corpora are kept as separate `Corpus` objects and are never merged.
That is guardrail 13, and merging them is the easy mistake to make: an HP
capability claim that happens to share a number with a row of the account's
technographics would otherwise "verify" against data that says nothing about HP.
So routing is decided first, and a claim routed to one corpus is never retried
against the other - failing verification is the correct outcome, not a reason to
look somewhere else.

The HP corpus is already guardrail-filtered for this account's country by
`approve_facts`, so anything withheld from a recommendation is equally
unavailable to the evaluator.
"""

import logging
import re

from app.services.extractors.grounding import (
    Corpus, build_corpus, corpus_from_texts, normalize_hp_product,
)
from app.services.hp.guardrails import (
    SUPERLATIVE_BLOCK_COUNTRIES, COMPETITOR_BLOCK_COUNTRIES, normalize_country,
)

logger = logging.getLogger(__name__)

SUBMITTED_DRAFT = "submitted_draft"
ACCOUNT_CORPUS = "account_corpus"
HP_FACT_CORPUS = "hp_fact_corpus"
PERSONA_CONTEXT = "persona_context"

# Surfaced in the UI's Data Sources panel, so the seller can see which source
# stands behind each part of the evaluation rather than reading one undivided
# "AI analysis".
AUTHORITY = {
    SUBMITTED_DRAFT: {
        "label": "Your draft",
        "may_establish": ["where a phrase sits in the message"],
        "never_establishes": ["any fact - writing a claim does not make it true"],
    },
    ACCOUNT_CORPUS: {
        "label": "Account data",
        "may_establish": ["facts about this account"],
        "never_establishes": ["HP product capability"],
    },
    HP_FACT_CORPUS: {
        "label": "Approved HP facts",
        "may_establish": ["HP product capability"],
        "never_establishes": ["any fact about this account"],
    },
    PERSONA_CONTEXT: {
        "label": "Persona context",
        "may_establish": ["the contact's role, department, seniority and remit"],
        "never_establishes": ["what the person thinks, wants, or has said"],
    },
}

# Claim-shaped superlatives. Deliberately narrow: "best practice" and "a great
# fit" are ordinary sales language, while "the world's most secure PC" is a
# claim HP restricts by market.
SUPERLATIVE_RE = re.compile(
    r"\b(world'?s\s+(?:most|best|first|only)|industry[- ]leading|"
    r"the\s+(?:most|best|fastest|safest)\s+\w+|"
    r"most\s+secure|unmatched|unrivalled|unrivaled|number\s*one|#1|"
    r"market[- ]leading|best[- ]in[- ]class)\b", re.I)

# Named competitors. A draft naming one is making a comparative claim whether or
# not it uses comparative words.
COMPETITOR_RE = re.compile(
    r"\b(lenovo|dell|apple|acer|asus|samsung|microsoft\s+surface|"
    r"huawei|toshiba|fujitsu|msi|razer)\b", re.I)

VERDICT_SUPPORTED = "supported"
VERDICT_UNSUPPORTED = "unsupported"
VERDICT_RESTRICTED = "restricted"
VERDICT_NOT_CHECKABLE = "not_checkable"


def _text(value) -> str:
    return " ".join(str(value or "").split())


class EvaluatorSources:
    """The four sources, assembled for one account and one draft."""

    def __init__(self, account_id, company_name, country, account, hp, persona,
                 draft, hp_fact_count, hp_available):
        self.account_id = account_id
        self.company_name = company_name
        self.country = country
        self.account = account          # Corpus - account facts only
        self.hp = hp                    # Corpus - HP facts only. Never merged.
        self.persona = persona or {}
        self.draft = str(draft or "")
        self.hp_fact_count = hp_fact_count
        self.hp_available = hp_available
        self.superlatives_blocked = bool(country) and country in SUPERLATIVE_BLOCK_COUNTRIES
        self.competitor_claims_blocked = bool(country) and country in COMPETITOR_BLOCK_COUNTRIES

    # -- submitted draft: spans, and nothing else ---------------------------

    def locate(self, phrase):
        """(start, end) of `phrase` in the draft, or None.

        Located by searching the draft, never taken from the model. Whitespace
        is normalised on both sides so a reflowed quotation still matches, but
        the span returned indexes the original text.
        """
        needle = _text(phrase).lower()
        if not needle:
            return None
        hay = self.draft.lower()
        at = hay.find(needle)
        if at >= 0:
            return (at, at + len(needle))

        # Fall back to a whitespace-insensitive search: build a regex that lets
        # any run of whitespace match any other.
        pattern = r"\s+".join(re.escape(tok) for tok in needle.split())
        found = re.search(pattern, hay)
        return (found.start(), found.end()) if found else None

    # -- routing: decided before verification, never revisited ---------------

    def route(self, text):
        """Which corpus has authority over this claim.

        A claim naming an HP line is an HP capability claim and is answerable
        only by the HP fact corpus. Everything else is an account claim.
        """
        return HP_FACT_CORPUS if normalize_hp_product(text) else ACCOUNT_CORPUS

    def verify_claim(self, text, label="claim"):
        """Check one claim against the single source that has authority over it.

        Returns a verdict dict. `not_checkable` is an honest answer and is used
        whenever the claim carries nothing deterministically checkable - it is
        reported as such rather than being quietly upgraded to supported.
        """
        claim = _text(text)
        if not claim:
            return {"claim": "", "verdict": VERDICT_NOT_CHECKABLE, "reasons": []}

        routed = self.route(claim)
        corpus = self.hp if routed == HP_FACT_CORPUS else self.account
        reasons, checked = [], []

        # A restricted claim fails on the rule, whatever the corpus says.
        if self.superlatives_blocked:
            hit = SUPERLATIVE_RE.search(claim)
            if hit:
                checked.append("superlative")
                reasons.append("superlative claim %r is not permitted in %s "
                               "(guardrail 2)" % (hit.group(0), self.country.title()))
        if self.competitor_claims_blocked:
            hit = COMPETITOR_RE.search(claim)
            if hit:
                checked.append("competitor")
                reasons.append("naming %s is a competitor comparison claim, not "
                               "permitted in %s (guardrails 3-4)"
                               % (hit.group(0), self.country.title()))
        # A restriction does not short-circuit the rest. One sentence can carry
        # both a blocked superlative and an unsourced figure, and a seller
        # fixing only the problem they were shown would resubmit and fail again.
        restricted = bool(reasons)

        numbers = corpus.unsourced_numbers(claim)
        if numbers:
            checked.append("numbers")
            reasons.append("%s not found in %s: %s"
                           % ("figure" if len(numbers) == 1 else "figures",
                              AUTHORITY[routed]["label"], ", ".join(sorted(set(numbers)))))
        urls = corpus.unsourced_urls(claim)
        if urls:
            checked.append("urls")
            reasons.append("link not found in %s: %s"
                           % (AUTHORITY[routed]["label"], ", ".join(sorted(set(urls)))))

        if routed == HP_FACT_CORPUS and not self.hp_available:
            checked.append("hp_corpus")
            reasons.append("no approved HP fact corpus exists for this account, "
                           "so an HP capability claim cannot be verified")

        if restricted:
            verdict = VERDICT_RESTRICTED
        elif reasons:
            verdict = VERDICT_UNSUPPORTED
        elif checked or _NUMBER_RE.search(claim):
            verdict = VERDICT_SUPPORTED
        else:
            verdict = VERDICT_NOT_CHECKABLE

        return {"claim": claim, "verdict": verdict, "routed_to": routed,
                "reasons": reasons, "checked": checked}

    # -- persona context: role facts only -----------------------------------

    def persona_facts(self):
        """What may be asserted about the target, and nothing more."""
        p = self.persona
        return {
            "is_named_person": bool(p.get("is_named_person")),
            "title": p.get("title"),
            "department": p.get("department"),
            "normalized_department": p.get("normalized_department"),
            "seniority_band": p.get("seniority_band"),
            "influence_type": p.get("influence_type"),
        }

    def contact_names(self):
        """Names that may never appear in a simulated reaction or public post."""
        names = []
        full = _text(self.persona.get("name"))
        if full:
            names.append(full)
            names.extend(part for part in full.split() if len(part) > 2)
        return names

    # -- panel ---------------------------------------------------------------

    def as_panel(self):
        return {
            "sources": [
                {"id": SUBMITTED_DRAFT, **AUTHORITY[SUBMITTED_DRAFT],
                 "available": bool(self.draft)},
                {"id": ACCOUNT_CORPUS, **AUTHORITY[ACCOUNT_CORPUS],
                 "available": self.account.cell_count > 0,
                 "detail": "%d cells of uploaded account data" % self.account.cell_count},
                {"id": HP_FACT_CORPUS, **AUTHORITY[HP_FACT_CORPUS],
                 "available": self.hp_available,
                 "detail": ("%d guardrail-approved HP facts" % self.hp_fact_count)
                           if self.hp_available else "no approved HP facts for this account"},
                {"id": PERSONA_CONTEXT, **AUTHORITY[PERSONA_CONTEXT],
                 "available": bool(self.persona),
                 "detail": _text(self.persona.get("title")) or "role only"},
            ],
            "country": self.country or None,
            "superlatives_blocked": self.superlatives_blocked,
            "competitor_claims_blocked": self.competitor_claims_blocked,
        }


_NUMBER_RE = re.compile(r"\d[\d,\.]*")


def _account_texts(db, account_id):
    """Evidence the account's own extracted widgets already hold."""
    def widget(key):
        return (db["account_widgets"].find_one(
            {"account_id": account_id, "widget_key": key}) or {}).get("data") or {}

    exec_card = widget("exec_summary_card")
    texts = [exec_card.get("business_description") or "",
             exec_card.get("company_name") or "",
             exec_card.get("hq_location") or ""]
    texts += [str(t.get("topic_name") or "")
              for t in (widget("intent_topics_table").get("topics") or [])]
    texts += [str(t.get("headline") or t.get("text") or "")
              for t in (widget("opportunity_trigger_signals").get("triggers") or [])]
    texts += [str(s) for s in (widget("tech_stack_matrix").get("full_tech_stack") or [])]
    return [t for t in texts if t], exec_card


def _hp_fact_texts(db, account_id):
    """The HP facts approved for THIS account, with their conditions.

    Read from the recommendations widget rather than from the deck collection,
    because that widget holds what `approve_facts` already let through for this
    account's country. Reading the raw decks here would hand the evaluator
    claims the guardrails withheld from the recommendation.
    """
    widget = db["account_widgets"].find_one({
        "account_id": account_id,
        "widget_key": "technographic_hp_recommendations"}) or {}
    texts = []
    for rec in ((widget.get("data") or {}).get("recommendations") or []):
        for fact in (rec.get("approved_facts") or []):
            if not fact.get("kept"):
                continue
            texts.append(str(fact.get("text") or ""))
            texts.extend(str(c) for c in (fact.get("conditions") or []))
            texts.extend(str(q) for q in (fact.get("qualifiers") or []))
        for key in ("hp_family", "device_type", "category_name"):
            if rec.get(key):
                texts.append(str(rec[key]))
    return [t for t in texts if t]


def build(db, account_id, persona, message, dataset_records=None):
    """Assemble the four sources for one evaluation."""
    account_texts, exec_card = _account_texts(db, account_id)

    # The uploaded rows themselves, when the extractor already read them.
    records = dataset_records or {}
    account = build_corpus({**records, "widget_evidence":
                            [{"text": t} for t in account_texts]})

    hp_texts = _hp_fact_texts(db, account_id)
    hp = corpus_from_texts(hp_texts)

    company = _text(exec_card.get("company_name"))
    if not company:
        account_doc = db["accounts"].find_one({"_id": _oid(account_id)}) or {}
        company = _text(account_doc.get("name"))
    location = _text(exec_card.get("hq_location"))
    if not location:
        account_doc = db["accounts"].find_one({"_id": _oid(account_id)}) or {}
        location = _text(account_doc.get("hq_location"))

    return EvaluatorSources(
        account_id=account_id,
        company_name=company,
        country=normalize_country(location),
        account=account,
        hp=hp,
        persona=persona,
        draft=message,
        hp_fact_count=len(hp_texts),
        hp_available=bool(hp_texts),
    )


def _oid(account_id):
    from bson import ObjectId
    try:
        return ObjectId(str(account_id))
    except Exception:
        return account_id
