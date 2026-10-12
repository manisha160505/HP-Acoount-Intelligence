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

    offered proof     may establish  what an HP case study or Rulebook line the
                                     evaluation SHOWED says - its own figures
                      never          any fact about this account

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

Offered proof is the one addition, and it is not a second place to look. The
evaluation shows the model HP case studies and Rulebook "may state" lines and
tells it to recommend citing them; the rewrite was then verified against two
corpora that hold neither, so a seller who ticked "cite the case study" had the
rewrite rejected for the study's own figures (AEON, one-pager: "figures not
found in Account data: 128, 13"). Each offered item keeps its own corpus, and a
figure counts only where the sentence is ABOUT that item - it names the customer,
shares its wording, or is an HP capability claim. "AEON runs 128 stores" still
fails: nothing offered is about AEON.
"""

import logging
import re

from app.services.extractors.grounding import (
    build_corpus,
    corpus_from_texts,
    normalize_hp_product,
)
from app.services.hp.guardrails import (
    COMPETITOR_BLOCK_COUNTRIES,
    SUPERLATIVE_BLOCK_COUNTRIES,
    normalize_country,
)
from app.services.regen import store as widget_store

logger = logging.getLogger(__name__)

SUBMITTED_DRAFT = "submitted_draft"
ACCOUNT_CORPUS = "account_corpus"
HP_FACT_CORPUS = "hp_fact_corpus"
PERSONA_CONTEXT = "persona_context"
OFFERED_PROOF = "offered_proof"

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
    OFFERED_PROOF: {
        "label": "HP case studies and positioning shown with this evaluation",
        "may_establish": ["what that case study or Rulebook line itself says"],
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


# How many content words a sentence must share with an offered case study to
# count as being about it, when it does not name the customer. Three keeps
# "cut downtime across stores" tied to its study without letting one shared
# word ("stores") carry an unrelated figure across.
OFFERED_SHARED_WORDS = 3
_WORD_RE = re.compile(r"[a-z][a-z'-]{3,}")
_STOP_WORDS = frozenset(
    ["that", "this", "with", "from", "have", "been", "their", "they", "them", "were", "will", "would", "could", "should", "about", "into", "over", "under", "across", "than", "then", "when", "which", "while", "where", "your", "yours", "also", "more", "most", "some", "such", "only", "very", "after", "before", "through", "because", "being"])


# The length of a meeting being asked for: "a 15-minute call", "30 minutes on
# Thursday?". It is a request, not a fact about anyone, so there is nothing for
# a source to hold - yet it was checked as a figure, and a rewrite whose call to
# action asked for "a 15-minute call" was refused for the number 15.
_DURATION_RE = re.compile(r"\b\d{1,3}(?:\s*-\s*|\s+)?(?:minutes?|mins?|hours?|hrs?)\b", re.I)
_ASK_RE = re.compile(
    r"\b(call|chat|meeting|meet|conversation|demo|session|catch-?up|intro|"
    r"introduction|walkthrough|walk-through|briefing|coffee|discussion|slot)\b", re.I)


def _without_ask_durations(claim: str) -> str:
    """The claim with a requested meeting length taken out, for figure checks.

    Only where the sentence is an ask - it names a call or a meeting, or is a
    question. "We cut downtime by 30 minutes per device" is a claim and keeps
    its number.
    """
    if not _DURATION_RE.search(claim):
        return claim
    if _ASK_RE.search(claim) or claim.rstrip().endswith("?"):
        return _DURATION_RE.sub(" ", claim)
    return claim


def _content_words(text) -> set:
    return {w for w in _WORD_RE.findall(str(text or "").lower()) if w not in _STOP_WORDS}


class EvaluatorSources:
    """The four sources, assembled for one account and one draft."""

    def __init__(self, account_id, company_name, country, account, hp, persona,  # noqa: PLR0913, PLR0917 - long signature predates the lint gate
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
        # [(item, Corpus)] - one corpus per offered item, never pooled.
        self.offered = []
        self._draft_corpus = None
        self.superlatives_blocked = bool(country) and country in SUPERLATIVE_BLOCK_COUNTRIES
        self.competitor_claims_blocked = bool(country) and country in COMPETITOR_BLOCK_COUNTRIES

    # -- offered proof: what the evaluation itself put in front of the model --

    def offer(self, proof=(), positioning=()):
        """Register the case studies and Rulebook lines this evaluation showed.

        `proof` is `proof_available` and `positioning` is `rulebook_positioning`,
        exactly as stored on the evaluation, so the rewrite is checked against
        the same items the recommendations were written from.
        """
        self.offered = []
        for point in (proof or ()):
            text = _text((point or {}).get("text"))
            if text:
                item = {"kind": "case_study", "text": text,
                        "customer": _text(point.get("customer")),
                        "line": _text(point.get("line"))}
                self.offered.append((item, corpus_from_texts([text, item["customer"]])))
        for row in (positioning or ()):
            for fact in ((row or {}).get("allowed") or ()):
                text = _text(fact)
                if text:
                    item = {"kind": "positioning", "text": text, "customer": "",
                            "line": _text(row.get("line"))}
                    self.offered.append((item, corpus_from_texts([text])))
        return self

    def offered_items(self):
        return [item for item, _corpus in self.offered]

    def _about(self, claim: str, item: dict, hp_claim: bool) -> bool:
        """Is this sentence talking about that offered item?"""
        low = claim.lower()
        if item["customer"] and item["customer"].lower() in low:
            return True
        # Rulebook positioning is HP capability, so it answers HP claims only.
        if item["kind"] == "positioning":
            return hp_claim
        if hp_claim:
            return True
        shared = _content_words(claim) & _content_words(item["text"])
        return len(shared) >= OFFERED_SHARED_WORDS

    def _offered_holds(self, claim: str, token: str, hp_claim: bool, urls=False) -> bool:
        for item, corpus in self.offered:
            missing = corpus.unsourced_urls(token) if urls else corpus.unsourced_numbers(token)
            if not missing and self._about(claim, item, hp_claim):
                return True
        return False

    def untraceable_figures(self, text) -> list:
        """Figures in `text` that no source at all holds - not the account's
        data, not HP's approved facts, not the draft, not anything offered.

        Used on a RECOMMENDATION before it is offered to the seller: one that
        carries such a figure cannot survive the rewrite check, so ticking it
        would only produce an error.
        """
        claim = _without_ask_durations(_text(text))
        if not claim:
            return []
        if self._draft_corpus is None:
            self._draft_corpus = corpus_from_texts([self.draft])
        missing = set(self.account.unsourced_numbers(claim))
        for corpus in [self.hp, self._draft_corpus] + [c for _i, c in self.offered]:
            missing &= set(corpus.unsourced_numbers(claim))
            if not missing:
                break
        return sorted(missing)

    def untraceable_links(self, text) -> list:
        """Links in `text` that no source at all holds. The URL twin of
        `untraceable_figures`, for the same reason: a suggestion that adds one
        cannot survive the rewrite check."""
        claim = _text(text)
        if not claim:
            return []
        if self._draft_corpus is None:
            self._draft_corpus = corpus_from_texts([self.draft])
        missing = set(self.account.unsourced_urls(claim))
        for corpus in [self.hp, self._draft_corpus] + [c for _i, c in self.offered]:
            missing &= set(corpus.unsourced_urls(claim))
            if not missing:
                break
        return sorted(missing)

    def introduces(self, text) -> dict:
        """What `text` would ADD that this market or these sources do not allow.

        {"superlative": str|None, "competitor": str|None}. A term already in
        the seller's draft is not introduced by a suggestion that mentions it -
        "remove 'the world's most secure'" names the phrase in order to take it
        out, and must stay something the seller can tick.
        """
        claim, draft = _text(text), self.draft
        out = {"superlative": None, "competitor": None}
        if self.superlatives_blocked:
            hit = next((m.group(0) for m in SUPERLATIVE_RE.finditer(claim)
                        if m.group(0).lower() not in draft.lower()), None)
            out["superlative"] = hit
        if self.competitor_claims_blocked:
            hit = next((m.group(0) for m in COMPETITOR_RE.finditer(claim)
                        if m.group(0).lower() not in draft.lower()), None)
            out["competitor"] = hit
        return out

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

    def _draft_holds(self, token: str, urls=False) -> bool:
        if self._draft_corpus is None:
            self._draft_corpus = corpus_from_texts([self.draft])
        missing = (self._draft_corpus.unsourced_urls(token) if urls
                   else self._draft_corpus.unsourced_numbers(token))
        return not missing

    def verify_claim(self, text, label="claim", draft_ok=False):
        """Check one claim against the single source that has authority over it.

        Returns a verdict dict. `not_checkable` is an honest answer and is used
        whenever the claim carries nothing deterministically checkable - it is
        reported as such rather than being quietly upgraded to supported.

        `draft_ok` is for text that COMMENTS on the draft rather than making a
        claim of its own - the simulated reaction. "Someone in this role would
        want proof behind the 40% claim" repeats the seller's figure in order to
        question it; it asserts nothing, so a figure or link the draft itself
        contains is not held against it. Never set for the draft's own phrases
        or for a rewrite: there the draft is the thing being checked.
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
                reasons.append("superlative claim %r is not permitted in %s"
                               % (hit.group(0), self.country.title()))
        if self.competitor_claims_blocked:
            hit = COMPETITOR_RE.search(claim)
            if hit:
                checked.append("competitor")
                reasons.append("naming %s is a competitor comparison claim, not "
                               "permitted in %s"
                               % (hit.group(0), self.country.title()))
        # A restriction does not short-circuit the rest. One sentence can carry
        # both a blocked superlative and an unsourced figure, and a seller
        # fixing only the problem they were shown would resubmit and fail again.
        restricted = bool(reasons)

        hp_claim = routed == HP_FACT_CORPUS
        where = AUTHORITY[routed]["label"]
        if self.offered:
            where += " or the HP proof shown with this evaluation"
        via_offered = False
        # Guidance for a repair, never a second chance at the verdict. A figure
        # the OTHER corpus holds was put in a sentence the routed corpus has
        # authority over - "AEON's 20,000 staff need HP EliteBook" is an HP
        # claim, so 20,000 is checked against HP facts and fails. That is
        # correct (guardrail 13) and stays a failure; the hint only says the
        # way out is two sentences, not a different number.
        other = self.account if hp_claim else self.hp
        other_label = AUTHORITY[ACCOUNT_CORPUS if hp_claim else HP_FACT_CORPUS]["label"]
        hints = []

        numbers = corpus.unsourced_numbers(_without_ask_durations(claim))
        if numbers:
            checked.append("numbers")
            left = [n for n in numbers if not self._offered_holds(claim, n, hp_claim)]
            via_offered = via_offered or len(left) < len(numbers)
            if draft_ok:
                left = [n for n in left if not self._draft_holds(n)]
            if left:
                reasons.append("%s not found in %s: %s"
                               % ("figure" if len(set(left)) == 1 else "figures",
                                  where, ", ".join(sorted(set(left)))))
                elsewhere = sorted({n for n in left if not other.unsourced_numbers(n)})
                if elsewhere:
                    hints.append({"kind": "mixed_sentence", "figures": elsewhere,
                                  "held_by": other_label})
        urls = corpus.unsourced_urls(claim)
        if urls:
            checked.append("urls")
            left = [u for u in urls
                    if not self._offered_holds(claim, u, hp_claim, urls=True)]
            via_offered = via_offered or len(left) < len(urls)
            if draft_ok:
                left = [u for u in left if not self._draft_holds(u, urls=True)]
            if left:
                reasons.append("link not found in %s: %s"
                               % (where, ", ".join(sorted(set(left)))))

        # An HP claim an offered case study or Rulebook line answered is
        # verified by that item; the missing recommendations corpus is then
        # not what stands behind it.
        if routed == HP_FACT_CORPUS and not self.hp_available and not via_offered:
            checked.append("hp_corpus")
            reasons.append("there are no approved HP facts on file for this "
                           "account, so this HP claim can't be checked")

        if restricted:
            verdict = VERDICT_RESTRICTED
        elif reasons:
            verdict = VERDICT_UNSUPPORTED
        elif checked or _NUMBER_RE.search(claim):
            verdict = VERDICT_SUPPORTED
        else:
            verdict = VERDICT_NOT_CHECKABLE

        return {"claim": claim, "verdict": verdict, "routed_to": routed,
                "reasons": reasons, "checked": checked,
                "via_offered_proof": via_offered, "hints": hints}

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
        return (widget_store.get(account_id, key, db=db) or {}).get("data") or {}

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
    widget = widget_store.get(account_id, "technographic_hp_recommendations", db=db) or {}
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
