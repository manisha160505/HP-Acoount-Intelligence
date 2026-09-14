"""Turning an account's data into documents the graph extractor can read.

Two rules shape everything here.

**One document per logical unit, never a monolith.** The account's technology
stack is one document, its intent topics another, each HP product family
another. A single 300KB blob would chunk across unrelated subjects and produce
exactly the association error this layer exists to avoid - the transcript's
"gaming for Astra Limited", where a new-office chunk and a gaming chunk landed
together.

**A document id names the logical unit and nothing else.** Not the version, not
a content hash. An id that moved when content changed would leave the previous
document orphaned in the index instead of replaced, which is the documented
LightRAG failure: *"Modified content gets a new ID; old chunks remain until
explicit deletion."* Version and fingerprint are metadata, held in
`retrieval_index_state`.

Documents are written as labelled prose rather than raw JSON. The extractor
reads text, and the meeting is explicit that the labels have to survive: *"keep
a widget structure in which all things are properly labeled."* Every checkable
line carries its evidence id inline, so a citation can be resolved afterwards.
"""

import hashlib
import json
import logging

from app.database.mongodb import get_db
from app.services.retrieval.evidence import EvidenceBuilder

logger = logging.getLogger(__name__)

MAX_HP_FACTS_PER_FAMILY = 40


def _text(value) -> str:
    """Scalar text only.

    A dict or list reaching this would be str()-ed into the corpus as a Python
    repr - "Entry path: {'timeline': '0-90 days', 'target_contacts': [...]}" -
    which is not prose, chunks badly and teaches the graph nothing. Structured
    values are rendered explicitly by their caller or not at all.
    """
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    return " ".join(str(value if value is not None else "").split())


def _slug(value) -> str:
    import re
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", str(value or ""))).strip("_").lower()


def fingerprint(payload) -> str:
    """Content identity of one document."""
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Document:
    """One unit of the corpus: an id, its text, its citation path, its evidence."""

    def __init__(self, doc_id, unit_key, feature, title, lines, evidence_rows,
                 source_payload):
        self.doc_id = doc_id
        self.unit_key = unit_key
        self.feature = feature
        self.title = title
        self.lines = [l for l in lines if l]
        self.evidence_rows = evidence_rows
        self.fingerprint = fingerprint(source_payload)

    @property
    def file_path(self) -> str:
        """What a citation renders as."""
        return "%s/%s" % (self.feature, self.unit_key)

    @property
    def text(self) -> str:
        return "%s\n\n%s" % (self.title, "\n".join(self.lines))

    def is_empty(self) -> bool:
        return not self.lines


def _doc_id(account_id, index, feature, unit_key) -> str:
    """Short, stable, unique within an index.

    The evidence id is written inline in the document text and echoed back by
    the model, so length costs tokens on both legs. The index is not in the id
    because a workspace already scopes one index, and the feature segment is
    dropped when it merely repeats the index name.
    """
    account = _slug(account_id)[:8]
    parts = ["a%s" % account]
    if _slug(feature) != _slug(index):
        parts.append(_slug(feature))
    parts.append(_slug(unit_key))
    return "_".join(parts)


def _widget(db, account_id, widget_key) -> dict:
    return (db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": widget_key}) or {}).get("data") or {}


def _build(account_id, index, feature, unit_key, title, source_payload, fill):
    """Assemble one document, letting `fill` write lines against a builder."""
    doc_id = _doc_id(account_id, index, feature, unit_key)
    builder = EvidenceBuilder(account_id, index, doc_id, feature)
    lines = fill(builder)
    return Document(doc_id, unit_key, feature, title, lines,
                    builder.rows, source_payload)


# ---------------------------------------------------------------------------
# Content Messaging corpus
# ---------------------------------------------------------------------------

def content_messaging_documents(account_id: str, index: str = "content_messaging") -> list:
    """The documents that feed Content Messaging.

    Sources are exactly the ones the 11-features reference assigns this feature
    - business description, full tech stack, intent topic + composite score,
    news events - plus the already-built priorities and HP plays that ABX
    Feature 15 names, and the guardrail-approved HP product facts.
    """
    db = get_db()
    docs = []

    context = _widget(db, account_id, "messaging_context_card")
    company = _text(context.get("company_name")) or _text(
        (db["accounts"].find_one({"_id": _oid(account_id)}) or {}).get("name"))

    # -- the account itself ---------------------------------------------------
    business = context.get("business_context") or {}
    if business:
        def fill_profile(b):
            out = []
            for field, label in (("business_description", "Business description"),
                                 ("industry", "Industry"),
                                 ("hq_location", "Headquarters"),
                                 ("employee_range", "Employee range"),
                                 ("revenue_range", "Revenue range")):
                value = _text(business.get(field))
                if value:
                    out.append("%s: %s" % (label, b.line(value, field=field)))
            return out
        docs.append(_build(account_id, index, "content_messaging", "account_profile",
                           "Account profile - %s" % company, business, fill_profile))

    # -- technology -----------------------------------------------------------
    tech = context.get("technology_evidence") or {}
    stack = tech.get("full_tech_stack") or []
    matrix = tech.get("category_matrix") or {}
    if stack or matrix:
        def fill_tech(b):
            out = []
            if stack:
                out.append("%s uses %d identified technologies." % (company, len(stack)))
            for category, items in sorted(matrix.items()):
                if items:
                    out.append("%s technology in %s: %s" % (
                        company, category,
                        b.line(", ".join(items), field=category)))
            uncategorised = [t for t in stack
                             if not any(t in v for v in matrix.values())]
            if uncategorised:
                out.append("Other technology in use: %s" % b.line(
                    ", ".join(uncategorised[:60]), field="Full Tech Stack"))
            return out
        docs.append(_build(account_id, index, "content_messaging", "technology_stack",
                           "Technology in use at %s" % company, tech, fill_tech))

    # -- intent ---------------------------------------------------------------
    intent = context.get("intent_evidence") or {}
    topics = intent.get("topics") or []
    if topics:
        def fill_intent(b):
            out = ["%s shows research intent across %d topics." % (company, len(topics))]
            for i, t in enumerate(topics):
                name = _text(t.get("topic_name"))
                score = _text(t.get("composite_score"))
                if not name:
                    continue
                claim = ("%s is researching %s (composite score %s)" % (company, name, score)
                         if score else "%s is researching %s" % (company, name))
                out.append(b.line(claim, field="Topic", record_id=i))
            return out
        docs.append(_build(account_id, index, "content_messaging", "intent_topics",
                           "Research intent at %s" % company, intent, fill_intent))

    # -- news / triggers ------------------------------------------------------
    news = context.get("news_evidence") or {}
    triggers = news.get("triggers") or []
    if triggers:
        def fill_news(b):
            out = []
            for i, t in enumerate(triggers):
                headline = _text(t.get("event_headline"))
                if not headline:
                    continue
                date = _text(t.get("event_date"))
                kind = _text(t.get("event_type"))
                claim = headline
                if date:
                    claim += " (%s)" % date
                url = _text(t.get("source_url"))
                line = b.line(claim, field="event_headline", record_id=i,
                              publisher=_text(t.get("source_publisher")),
                              source_url=url)
                out.append("%s%s%s" % (
                    ("%s: " % kind) if kind else "", line,
                    (" Source: %s" % url) if url else ""))
            return out
        docs.append(_build(account_id, index, "content_messaging", "news_triggers",
                           "Recent events at %s" % company, news, fill_news))

    # -- already-built priorities and plays (ABX Feature 15 section 2) ---------
    #
    # These are the widget keys the features actually write - checked against
    # the stored widgets rather than guessed from the feature name.
    plays = _widget(db, account_id, "opportunity_narrative_plays")
    if plays:
        def fill_plays(b):
            out = []
            for i, play in enumerate(plays.get("opportunity_plays") or []):
                title = _text(play.get("title"))
                if not title:
                    continue
                out.append("Opportunity play: %s"
                           % b.line(title, field="title", record_id=play.get("play_key") or i))
                capability = _text(play.get("hp_capability"))
                if capability:
                    out.append("  HP capability: %s"
                               % b.line(capability, field="hp_capability",
                                        record_id=play.get("play_key") or i))
                # The account-side reason the play exists. Each entry carries
                # its OWN dataset and field - a play restates a technographics
                # cell or an intent topic, it does not originate the fact. Those
                # are passed through so the citation names the real source
                # rather than the document the play was assembled in.
                for j, ev in enumerate(play.get("account_evidence") or []):
                    statement = _text(ev.get("statement") or ev.get("quote"))
                    if statement:
                        out.append("  Account evidence: %s"
                                   % b.line(statement,
                                            field=_text(ev.get("field")) or "account_evidence",
                                            record_id="%s:%d" % (play.get("play_key") or i, j),
                                            dataset=_text(ev.get("dataset")),
                                            quote=_text(ev.get("quote"))))
                entry = play.get("entry_path")
                if isinstance(entry, dict):
                    timeline = _text(entry.get("timeline"))
                    if timeline:
                        out.append("  Suggested timeline: %s"
                                   % b.line(timeline, field="entry_path.timeline",
                                            record_id=play.get("play_key") or i))
            return out
        docs.append(_build(account_id, index, "content_messaging", "opportunity_plays",
                           "HP opportunity plays for %s" % company, plays, fill_plays))

    signals = _widget(db, account_id, "news_signals_feed")
    if signals:
        def fill_signals(b):
            out = []
            for i, card in enumerate(signals.get("signals") or []):
                headline = _text(card.get("headline"))
                if not headline:
                    continue
                date = _text(card.get("event_date"))
                category = _text(card.get("category"))
                claim = headline + (" (%s)" % date if date else "")
                line = b.line(claim, field="headline",
                              record_id=card.get("signal_id") or i,
                              publisher=_text(card.get("source_publisher")),
                              source_url=_text(card.get("source_url")))
                out.append("%s%s" % (("%s signal: " % category) if category else "", line))
                sentence = _text(card.get("evidence_sentence"))
                if sentence:
                    # The sentence was pulled from the same article as the
                    # headline above it, so it carries the same publisher and
                    # link. Omitting them here made a quoted sentence look
                    # unsourced while the headline beside it linked out.
                    out.append("  Evidence: %s"
                               % b.line(sentence, field="evidence_sentence",
                                        record_id=card.get("signal_id") or i,
                                        publisher=_text(card.get("source_publisher")),
                                        source_url=_text(card.get("source_url"))))
                url = _text(card.get("source_url"))
                publisher = _text(card.get("source_publisher"))
                if publisher or url:
                    out.append("  Reported by %s. %s" % (publisher or "an external source", url))
            return out
        docs.append(_build(account_id, index, "content_messaging", "news_signals",
                           "Interpreted signals for %s" % company, signals, fill_signals))

    # -- the account's technology categories, as the map already grouped them --
    techmap = _widget(db, account_id, "technographic_map")
    if techmap:
        def fill_map(b):
            out = []
            for i, cat in enumerate(techmap.get("categories") or []):
                name = _text(cat.get("category_name") or cat.get("name"))
                if not name:
                    continue
                vendors = cat.get("vendors") or cat.get("technologies") or []
                vendor_text = ", ".join(_text(v.get("name") if isinstance(v, dict) else v)
                                        for v in vendors[:25] if v)
                if vendor_text:
                    out.append("%s category %s: %s"
                               % (company, name,
                                  b.line(vendor_text, field="category", record_id=i)))
                meaning = _text(cat.get("what_it_means_for_hp") or cat.get("hp_relevance"))
                if meaning:
                    out.append("  What this means for HP: %s"
                               % b.line(meaning, field="what_it_means_for_hp", record_id=i))
            return out
        docs.append(_build(account_id, index, "content_messaging", "technology_categories",
                           "Technology categories at %s" % company, techmap, fill_map))

    # -- approved HP facts, one document per product family --------------------
    docs.extend(_hp_documents(db, account_id, index))

    return [d for d in docs if not d.is_empty()]


def _hp_documents(db, account_id, index) -> list:
    """HP capability, split by product family.

    One document per family rather than one HP document, so the graph relates a
    family to the account problem it answers instead of relating every HP fact
    to everything. Read from the recommendations widget, which holds only what
    the country guardrails already approved for this account.
    """
    recs = _widget(db, account_id, "technographic_hp_recommendations")
    by_family = {}
    for rec in (recs.get("recommendations") or []):
        family = _text(rec.get("hp_family")) or "HP"
        entry = by_family.setdefault(family, {"facts": [], "meta": rec})
        for fact in (rec.get("approved_facts") or []):
            if fact.get("kept") and _text(fact.get("text")):
                entry["facts"].append(fact)

    docs = []
    for family, entry in sorted(by_family.items()):
        facts = entry["facts"][:MAX_HP_FACTS_PER_FAMILY]
        if not facts:
            continue
        meta = entry["meta"]

        def fill_hp(b, facts=facts, meta=meta, family=family):
            out = []
            device = _text(meta.get("device_type"))
            category = _text(meta.get("category_name"))
            if device or category:
                out.append("%s addresses %s." % (family, category or device))
            for i, fact in enumerate(facts):
                line = b.line(fact.get("text"), field="approved_fact",
                              record_id=fact.get("slide_id"))
                conditions = [c for c in (fact.get("conditions") or []) if _text(c)]
                out.append(line)
                if conditions:
                    out.append("  Condition: %s" % _text("; ".join(conditions))[:400])
            return out

        docs.append(_build(account_id, index, "hp_products", "family_%s" % _slug(family),
                           "HP capability - %s" % family,
                           {"family": family, "facts": facts}, fill_hp))
    return docs


def _oid(account_id):
    from bson import ObjectId
    try:
        return ObjectId(str(account_id))
    except Exception:
        return account_id


def fingerprints(documents) -> dict:
    """The map `index_state` compares against to decide whether to build."""
    return {d.doc_id: {"fingerprint": d.fingerprint, "unit_key": d.unit_key}
            for d in documents}
