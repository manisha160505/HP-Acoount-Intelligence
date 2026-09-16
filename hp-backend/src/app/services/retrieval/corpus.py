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
import re

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
        self.lines = [line for line in lines if line]
        self.evidence_rows = evidence_rows
        # Fingerprinted on the text that actually gets indexed, not on the raw
        # source it was built from.
        #
        # Those differ whenever the BUILDER changes rather than the data. The
        # narrative documents were switched from paragraph-level to
        # sentence-level evidence - the indexed text changed completely - and
        # because the underlying pages had not changed, every document compared
        # equal and the improvement silently never reached the index. A
        # fingerprint that misses a change to its own document's content cannot
        # do the one job it has.
        #
        # `source_payload` is still taken so a builder can fold in anything the
        # text does not show; it is combined with the text rather than replacing
        # it.
        self.fingerprint = fingerprint(
            {"text": self.text, "source": source_payload})

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
            for _i, fact in enumerate(facts):
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


# ---------------------------------------------------------------------------
# Executive Dashboard corpus
# ---------------------------------------------------------------------------

# ABX Feature 1, "Clean and prepare the data": "Convert strategy statements into
# a standard priority list (AI, workforce productivity, hybrid work, expansion,
# security, fleet refresh, print/workflow, sustainability...)". The vocabulary is
# the document's, not ours, which is what makes it safe to select narrative pages
# with - a page is chosen because it discusses a theme ABX names, not because it
# matched a phrase invented here.
PRIORITY_THEMES = {
    "AI": r"\bAI\b|artificial intelligence|machine learning|generative",
    "workforce productivity": r"workforce|productivity|employee experience|talent|upskill",
    "hybrid work": r"hybrid work|remote work|flexible work|work from",
    "expansion": r"expansion|new market|acquisition|capacity|greenfield",
    "security": r"cyber ?security|information security|data protection|data privacy",
    "fleet refresh": r"\bfleet\b|device refresh|hardware refresh|IT infrastructure|data cent",
    "print/workflow": r"printing|document workflow|paperless|digiti[sz]ation of document",
    "sustainability": r"sustainab|net zero|emission|\bESG\b|decarbon|renewable",
    "cost efficiency": r"cost efficien|cost reduction|operational excellence|margin improvement",
}

# How much filing narrative may enter the index, measured in characters. A full
# annual report is ~1.5M characters; extracting a graph from all of it would cost
# hours and thousands of LLM calls to describe pages about branch openings.
# Pages are ranked by how many ABX themes they discuss and taken until the budget
# is spent, so what survives is the most strategy-dense part of the document.
# Financial pages are never subject to this - they are the point.
NARRATIVE_BUDGET_CHARS = 160000
MAX_NARRATIVE_PAGES_PER_DOCUMENT = 6
MAX_DETAIL_CLAIMS = 60

# A page has to discuss more than one of ABX's themes to count as strategy
# narrative, and has to be written in sentences. One theme is a passing mention;
# a page that is all fragments is a register or a table of names that happens to
# contain the word.
MIN_NARRATIVE_THEMES = 2
MIN_SENTENCE_SHARE = 0.5


def _sentence_share(text) -> float:
    """The share of a page's characters that live inside real sentences.

    Counting words does not separate narrative from a table: an awards register
    is nothing but words, and on this report it scores as highly as a strategy
    chapter. Sentences do separate them cleanly - measured across the 2025
    report, the certifications page scores 0.00 and the digital-transformation
    chapter 0.99, with the median page at 0.96.
    """
    import re
    parts = re.split(r"(?<=[.!?])\s+", " ".join(str(text or "").split()))
    total = sum(len(p) for p in parts)
    if not total:
        return 0.0
    inside = sum(len(p) for p in parts
                 if len(p) >= 60 and len(p.split()) >= 8
                 and p.rstrip().endswith((".", "!", "?")))
    return inside / float(total)


def _filing_documents(account_id, index, company) -> list:
    """Documents read from the account's filed PDFs.

    The filings are a registered dataset like any other, found through
    `account_data_files` - never a path on one machine. An account with no
    filings simply contributes no documents here, and the dashboard falls back
    to what the CSVs carry.
    """
    from app.services.extractors.datasets import DatasetFileMissing, dataset_file_paths
    from app.services.retrieval import financials, pdf

    try:
        files = dataset_file_paths(account_id, "compliance_filings", strict=False)
    except DatasetFileMissing:
        return []
    if not files:
        return []

    docs, all_claims, extractions = [], [], []
    for original_name, path in files:
        try:
            extracted = pdf.read_pdf(path)
        except pdf.PdfUnreadable:
            logger.exception("retrieval: cannot read filing %s", original_name)
            continue
        extracted["file"] = original_name
        claims, stats = financials.document_claims(extracted)
        extractions.append(extracted)
        all_claims.extend(claims)
        logger.info("retrieval: %s - %d page(s) kept, %d claim(s), %d page(s) "
                    "excluded", original_name, len(extracted["pages"]),
                    stats["claims"], len(extracted["excluded"]))

    docs.extend(_financial_documents(account_id, index, company, all_claims))
    docs.extend(_narrative_documents(account_id, index, company, extractions,
                                     _reporting_periods(all_claims)))
    return docs


def _reporting_periods(claims) -> dict:
    """{filename: the period that filing reports}, read from its own tables.

    A narrative sentence has no date of its own - a paragraph about digital
    infrastructure on page 120 states no year. What it does have is the document
    it came from, and that document's tables say plainly which period it
    reports: the annual report's comparatives run to FY2025, the July market
    report to FY2026.

    So the period is taken from the filing's own figures rather than parsed out
    of its filename, which would be guesswork and account-specific. It means
    "this evidence comes from the filing that reports FY2025", which is exactly
    what ABX's recency term needs and is checkable against the document.
    """
    from app.services.retrieval import financials

    latest = {}
    for claim in claims or []:
        name = claim.get("file")
        period = str(claim.get("period") or "")
        if not name or not period:
            continue
        current = latest.get(name)
        if current is None or financials.period_key(period) > financials.period_key(current):
            latest[name] = period
    # "FY2026 total" is the same reporting year as "2026-Jul"; the card wants
    # the year, not the row that happened to sort last.
    return {name: period.replace(" total", "").strip()
            for name, period in latest.items()}


def _metric_name(metric, section) -> str:
    """A metric named unambiguously within its table.

    A filing can state the same label twice under different headings - this
    report gives "Owners of the Parent" once under "Profit Attributable to:" and
    again under "Comprehensive Income Attributable to:", with different figures.
    The label alone would publish one of them under both, so the heading is part
    of the name whenever the table supplies one.
    """
    metric = _text(metric)
    section = _text(section)
    if not section or section.lower() in metric.lower():
        return metric
    return "%s - %s" % (section, metric)


def _claim_line(builder, claim, prefix=""):
    """One reported figure, written so the number and its period are inseparable.

    The evidence row carries the value, period and unit as fields as well as
    text, so whatever is published later is read back from the row rather than
    re-parsed out of this sentence.
    """
    # A percentage already carries its unit in the digits; appending it again
    # reads as "51% %".
    written = claim["value_text"]
    if not written.endswith("%"):
        written = "%s %s" % (written, claim["unit"])
    name = _metric_name(claim["metric"], claim.get("section"))
    sentence = "%s%s for %s: %s" % (prefix, name, claim["period"], written)
    return builder.line(
        sentence, field=name, record_id=claim["table_id"],
        dataset="compliance_filings", quote=claim["quote"],
        period=claim["period"], value=claim["value"], unit=claim["unit"],
        page=claim["page"], filing_label=claim["file"])


def _financial_documents(account_id, index, company, claims) -> list:
    """Reported figures, split into the multi-year summary and the rest.

    The summary table is its own document because it is the one a dashboard
    quotes: five years of revenue, profit, assets and equity, all in one unit,
    all for the whole company. Keeping it apart from the segment tables is the
    corpus-level form of ABX's "correct company/business unit" check - a chunk
    mixing the two would let the graph relate a division's revenue to the
    group's.
    """
    from app.services.retrieval import financials

    if not claims:
        return []

    monthly_files = _monthly_files(claims)
    docs = []
    summary_id = financials.summary_table(
        [c for c in claims if c["file"] not in monthly_files] or claims)
    summary_claims = [c for c in claims if c["table_id"] == summary_id]

    if summary_claims:
        unit = summary_claims[0]["unit"]
        source_file = summary_claims[0]["file"]
        page = summary_claims[0]["page"]

        def fill_summary(b):
            out = ["Reported financial figures for %s, read from %s page %s."
                   % (company, source_file, page),
                   "Every figure in this document is stated in %s." % unit]
            for metric, section in financials.metrics_in_table(summary_claims,
                                                               summary_id):
                rows = financials.series(summary_claims, metric, summary_id,
                                         section)
                if not rows:
                    continue
                trend = ", ".join("%s %s" % (r["period"], r["value_text"])
                                  for r in rows)
                out.append("%s by reporting period: %s (%s)."
                           % (_metric_name(metric, section), trend, unit))
                for row in rows:
                    out.append("  %s" % _claim_line(b, row))
            return out

        docs.append(_build(account_id, index, "executive_dashboard",
                           "financial_highlights",
                           "Reported financial highlights - %s" % company,
                           summary_claims, fill_summary))

    rest = [c for c in claims
            if c["table_id"] != summary_id and c["file"] not in monthly_files]
    rest = rest[:MAX_DETAIL_CLAIMS]
    if rest:
        def fill_detail(b):
            out = ["Further reported figures for %s, each carrying the table and "
                   "page it was read from." % company]
            for claim in rest:
                out.append(_claim_line(b, claim))
            return out
        docs.append(_build(account_id, index, "executive_dashboard",
                           "financial_detail",
                           "Further reported figures - %s" % company,
                           rest, fill_detail))

    market = [c for c in claims if c["file"] in monthly_files]
    if market:
        docs.extend(_market_documents(account_id, index, company, market))
    return docs


def _monthly_files(claims) -> set:
    """Filings that report by month rather than by financial year.

    Recognised by the periods their own tables carry - `financials` writes a
    month column as `2026-Jul` - so this holds for any account whose market data
    arrives monthly, under any naming convention. Nothing here reads a filename.
    """
    import re
    return {c["file"] for c in claims
            if re.match(r"^\d{4}-[A-Za-z]{3}$", str(c["period"]))}


def _market_documents(account_id, index, company, claims) -> list:
    """Market position, from the periodic market reports.

    One document, because these files are one series reported repeatedly rather
    than separate subjects. Only the most recent report contributes figures -
    each issue restates the whole year to date, so indexing all of them would
    register the same January volume many times over and let the graph read one
    month as several independent confirmations.
    """
    from app.services.retrieval import financials

    # The most recent report and the current table, chosen by the periods the
    # data itself carries. Sorting filenames would order "May'26" after "Jul'26"
    # and publish spring figures as the latest; picking the table with the most
    # columns would publish last year's complete twelve months in preference to
    # this year's seven.
    def newest(rows):
        # Full-year totals are ignored in this comparison. Every issue of a
        # monthly report carries a year-to-date total for the same year, so
        # totals tie and the tie-break would fall to whichever file came first -
        # which is how the March issue once beat the July one. The latest
        # *month* actually reported is what distinguishes them.
        months = [financials.period_key(r["period"]) for r in rows
                  if not str(r["period"]).lower().endswith("total")]
        return max(months) if months else (0, 0)

    latest_file = max({c["file"] for c in claims},
                      key=lambda f: newest([c for c in claims if c["file"] == f]))
    latest = [c for c in claims if c["file"] == latest_file]
    table_id = max({c["table_id"] for c in latest},
                   key=lambda t: newest([c for c in latest if c["table_id"] == t]))
    shares = [c for c in latest if c["unit"] == "%" and c["table_id"] == table_id]
    volumes = [c for c in latest if c["unit"] != "%" and c["table_id"] == table_id]

    def fill_market(b):
        out = ["Market position for %s, read from %s." % (company, latest_file)]
        for metric, section in financials.metrics_in_table(shares, table_id):
            rows = financials.series(shares, metric, table_id, section)
            if rows:
                out.append("%s by month: %s." % (
                    _metric_name(metric, section),
                    ", ".join("%s %s" % (r["period"], r["value_text"])
                              for r in rows)))
                out.append("  %s" % _claim_line(b, rows[-1], prefix="Most recent "))
        for metric, section in financials.metrics_in_table(volumes, table_id):
            rows = financials.series(volumes, metric, table_id, section)
            totals = [r for r in rows if str(r["period"]).lower().endswith("total")]
            if totals:
                out.append(_claim_line(b, totals[-1]))
        return out

    return [_build(account_id, index, "executive_dashboard", "market_position",
                   "Market position - %s" % company, latest, fill_market)]


def _narrative_documents(account_id, index, company, extractions,
                         reporting_periods=None) -> list:
    """Strategy narrative, selected by theme density and chunked into documents.

    Pages are scored by how many of ABX's named priority themes they discuss and
    taken in that order until the character budget is spent. The themes a page
    matched travel with it, so a priority assembled later can point at the pages
    that actually discuss it rather than at the report as a whole.
    """
    import re

    scored = []
    for extracted in extractions:
        for page in extracted.get("pages") or []:
            text = page.get("text") or ""
            themes = [name for name, pattern in PRIORITY_THEMES.items()
                      if re.search(pattern, text, re.I)]
            if len(themes) < MIN_NARRATIVE_THEMES:
                continue
            if _sentence_share(text) < MIN_SENTENCE_SHARE:
                # A certifications register or an awards table can mention
                # sustainability and security and still be a table of names and
                # dates. Indexing it teaches the graph that the account "has
                # security" without a sentence saying anything about why.
                continue
            scored.append((len(themes), extracted["file"], page, themes))

    scored.sort(key=lambda row: (-row[0], row[1], row[2]["page"]))

    chosen, spent = [], 0
    for _, file_name, page, themes in scored:
        size = len(page["text"])
        if spent + size > NARRATIVE_BUDGET_CHARS:
            continue
        spent += size
        chosen.append((file_name, page, themes))

    # Back into reading order, so one document holds neighbouring pages.
    chosen.sort(key=lambda row: (row[0], row[1]["page"]))

    docs = []
    for start in range(0, len(chosen), MAX_NARRATIVE_PAGES_PER_DOCUMENT):
        group = chosen[start:start + MAX_NARRATIVE_PAGES_PER_DOCUMENT]
        first_file = group[0][0]
        first_page, last_page = group[0][1]["page"], group[-1][1]["page"]
        unit_key = "strategy_%s_p%s_%s" % (_slug(first_file)[:24], first_page,
                                           last_page)

        def fill_narrative(b, group=group):
            out = []
            for file_name, page, themes in group:
                out.append("From %s, page %s. Themes discussed: %s."
                           % (file_name, page["page"], ", ".join(themes)))
                period = (reporting_periods or {}).get(file_name)
                for paragraph in _paragraphs(page["text"]):
                    if _is_indonesian(paragraph):
                        # Indexed so retrieval keeps its recall, but carries no
                        # evidence id, so it can never become a quote on a card.
                        out.append(paragraph)
                        continue
                    for sentence in _sentences(paragraph):
                        # Tested again per sentence, not only per paragraph. A
                        # page whose two columns interleave produces paragraphs
                        # that are mixed, and those read as English on balance
                        # while still containing Indonesian sentences - which is
                        # how 46 of them reached the cards after the paragraph
                        # test alone.
                        if _is_indonesian(sentence) or _is_interleaved(sentence):
                            out.append(sentence)
                            continue
                        line = b.line(sentence, field="filing_narrative",
                                      record_id="%s#p%s" % (file_name, page["page"]),
                                      dataset="compliance_filings",
                                      page=page["page"], filing_label=file_name,
                                      filing_period=period)
                        if line:
                            out.append(line)
            return out

        docs.append(_build(account_id, index, "executive_dashboard", unit_key,
                           "Strategy narrative - %s, %s pages %s-%s"
                           % (company, first_file, first_page, last_page),
                           [g[1]["text"] for g in group], fill_narrative))
    return docs


# Function words that carry a language and nothing else. Indonesian and English
# are compared against each other rather than either being thresholded on its
# own: a threshold has to be tuned to passage length and got it wrong on the
# first try, calling a wholly Indonesian paragraph English because it happened
# to be short. Which list wins does not depend on length at all.
_INDONESIAN_MARKERS = re.compile(
    r"\b(yang|dan|untuk|dengan|pada|dari|dalam|tidak|serta|adalah|ini|itu|akan|"
    r"telah|sebagai|oleh|juga|dapat|melalui|terhadap|kepada|antara|di|ke|atau|"
    r"karena|agar|bagi|para|secara|sehingga|tersebut|masih|lebih|hingga|maupun|"
    r"dengan|guna|sejak|setiap|lain)\b", re.I)

_ENGLISH_MARKERS = re.compile(
    r"\b(the|of|and|to|in|is|that|for|with|as|by|on|are|was|has|have|been|its|"
    r"this|these|which|from|their|also|such|through|between|while|will|been)\b",
    re.I)


def _is_indonesian(text) -> bool:
    """Whether a passage is the Indonesian half of a bilingual page.

    These filings print every page twice, Indonesian beside English. Both halves
    are indexed, because on a few pages the columns are not translations and
    dropping one would lose content. But only the English half is made
    *citable*: a card that quotes its source has to be readable by the person
    reading the card, and 56% of the first build's quotes were Indonesian.
    """
    body = str(text or "")
    if len(body.split()) < 6:
        return False
    return len(_INDONESIAN_MARKERS.findall(body)) > len(_ENGLISH_MARKERS.findall(body))


def _is_interleaved(text) -> bool:
    """Whether a passage is two columns welded together rather than one language.

    `_is_indonesian` asks which language *wins*; this asks whether both are
    present in strength, which is a different failure and invisible to that test:

        "Ancaman cybersecurity yang semakin tinggi juga akan The rising threat of
         cybersecurity will also drive meningkatkan permintaan terkait solusi
         keamanan demand for data security solutions"

    That reads as English on balance, so the language filter passed it and it
    reached a card. It is the Indonesian and English columns merged line by line,
    which happens when a page's gutter cannot be found.

    Geometry is the real fix and now handles all but three pages of this report.
    This is the guarantee for the rest: such a passage stays indexed, so
    retrieval keeps its recall, but never receives an evidence id and so can
    never be quoted at anyone.
    """
    body = str(text or "")
    if len(body.split()) < 8:
        return False
    return (len(_INDONESIAN_MARKERS.findall(body)) >= 3
            and len(_ENGLISH_MARKERS.findall(body)) >= 3)


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")


def _sentences(text, min_chars=60, max_chars=320) -> list:
    """A passage split into sentences a card can quote.

    The first build registered whole page chunks as evidence - a median of 903
    characters - and then printed one verbatim as the "supporting sentence".
    Chunking for a graph extractor and quoting for a human are different jobs;
    this does the second. Fragments below `min_chars` are joined onto their
    neighbour rather than dropped, so nothing is lost at a bad split point.
    """
    out, buffer = [], ""
    for part in _SENTENCE_END.split(" ".join(str(text or "").split())):
        part = part.strip()
        if not part:
            continue
        buffer = ("%s %s" % (buffer, part)).strip() if buffer else part
        if len(buffer) >= min_chars:
            out.append(buffer[:max_chars])
            buffer = ""
    if buffer:
        if out and len(buffer) < min_chars:
            out[-1] = ("%s %s" % (out[-1], buffer))[:max_chars]
        else:
            out.append(buffer[:max_chars])
    return out


# A line holding a bare number and nothing else. Bounded to four digits so a
# figure like "12,345" or a year in a sentence is untouched - this only matches a
# line that IS the number.
_PAGE_FURNITURE = re.compile(r"^\d{1,4}$")


def _paragraphs(text, min_chars=80, max_chars=900) -> list:
    """Readable paragraphs from a reconstructed page.

    Rebuilt tables arrive one row per line and prose one visual line per line, so
    lines are joined until they reach a usable length. Short fragments - a page
    header, a caption, a stray figure - are dropped rather than registered as
    claims nobody could check.

    A line that is nothing but a bare number is page furniture: a page number or
    a cross-reference sitting in the margin, which the coordinate rebuild gives
    its own row. Joined into a paragraph it lands mid-sentence, which is how a
    card came to read "the 271 Information Technology Solutions segment" and
    "increasing 205 demand". There are 877 such lines in this one report. Only
    narrative prose is filtered here; `financials.py` reads table rows and is
    untouched, and a lone number could not bind there anyway - a data row has to
    supply exactly as many figures as its header has columns.
    """
    out, buffer = [], []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if _PAGE_FURNITURE.match(stripped):
            continue
        if not stripped:
            if buffer:
                out.append(" ".join(buffer))
                buffer = []
            continue
        buffer.append(stripped)
        if sum(len(b) + 1 for b in buffer) >= max_chars:
            out.append(" ".join(buffer))
            buffer = []
    if buffer:
        out.append(" ".join(buffer))
    return [p for p in out if len(p) >= min_chars]


MAX_SIGNALS = 12
MAX_INTENT_TOPICS = 25
MAX_DEPARTMENTS = 12


def executive_dashboard_documents(account_id: str,
                                  index: str = "executive_dashboard") -> list:
    """The documents that feed the Executive Dashboard.

    Three sources, kept as separate documents throughout.

    **The account's filed documents** - annual reports and periodic market
    reports, registered under `compliance_filings`. These are the only place a
    *reported* financial figure exists; every other dataset carries a band.

    **The datasets the 11-features reference assigns Feature 1** - firmographics
    for identity, industry, HQ, employees and the revenue band, company
    hierarchy for parent and ultimate parent, job openings for the hiring
    signal.

    **The cleaned outputs of the features ABX Step 4 says to reuse** - *"reuse
    the cleaned Recent News, Stakeholder Map, Tech Landscape and Intent
    outputs"*. Reusing them rather than re-reading their CSVs is deliberate:
    those features already applied their own gates, and re-deriving the same
    facts here would produce a second, quietly different answer.

    What this index *generates* - the strategic priorities and the urgency score
    - is deliberately absent. A generated widget that fed back into its own
    corpus would change the corpus on every build and trigger the next one.
    """
    db = get_db()
    docs = []

    summary = _widget(db, account_id, "exec_summary_card")
    metrics = _widget(db, account_id, "exec_key_metrics")
    company = _text(summary.get("company_name")) or _text(
        (db["accounts"].find_one({"_id": _oid(account_id)}) or {}).get("name"))

    # -- identity -------------------------------------------------------------
    if summary or metrics:
        payload = {"summary": summary, "metrics": metrics}

        def fill_profile(b):
            out = []
            for field, label in (("business_description", "Business description"),
                                 ("industry_classification", "Industry"),
                                 ("hq_location", "Headquarters"),
                                 ("domain", "Website")):
                value = _text(summary.get(field))
                if value:
                    out.append("%s: %s" % (label, b.line(value, field=field,
                                                         dataset="firmographics")))
            employees = _text(metrics.get("employee_count"))
            if employees:
                out.append("Employee count band: %s"
                           % b.line(employees, field="employee_count",
                                    dataset="firmographics"))
            revenue = _text(metrics.get("revenue"))
            if revenue:
                # Named a band on purpose. It is a firmographic bucket, not a
                # figure the company reported, and the dashboard shows it beside
                # the filed revenue rather than instead of it.
                out.append("Revenue band reported by the firmographics dataset "
                           "(a band, not a filed figure): %s"
                           % b.line(revenue, field="revenue",
                                    dataset="firmographics"))
            return out

        docs.append(_build(account_id, index, "executive_dashboard",
                           "account_profile", "Account profile - %s" % company,
                           payload, fill_profile))

    # -- ownership ------------------------------------------------------------
    parent = _text(summary.get("parent_company"))
    ultimate = _text(summary.get("ultimate_parent"))
    if parent or ultimate:
        def fill_structure(b):
            out = []
            if parent:
                out.append("Parent company: %s"
                           % b.line(parent, field="parent_company",
                                    dataset="company_hierarchy"))
            if ultimate:
                out.append("Ultimate parent: %s"
                           % b.line(ultimate, field="ultimate_parent",
                                    dataset="company_hierarchy"))
            return out
        docs.append(_build(account_id, index, "executive_dashboard",
                           "corporate_structure",
                           "Corporate structure - %s" % company,
                           {"parent": parent, "ultimate": ultimate},
                           fill_structure))

    # -- hiring ---------------------------------------------------------------
    hiring = _widget(db, account_id, "exec_hiring_velocity")
    demand = _widget(db, account_id, "intent_hiring_demand")
    if hiring or demand:
        payload = {"hiring": hiring, "demand": demand}

        def fill_hiring(b):
            out = []
            count = _text(hiring.get("open_job_count")) or _text(
                demand.get("open_job_count"))
            if count:
                out.append("Open job postings: %s"
                           % b.line(count, field="open_job_count",
                                    dataset="job_openings"))
            roles = [_text(r) for r in (hiring.get("sample_roles") or []) if _text(r)]
            if roles:
                out.append("Roles currently being hired for: %s"
                           % b.line(", ".join(roles[:10]), field="sample_roles",
                                    dataset="job_openings"))
            for key, label in (("seniority_breakdown", "Hiring by seniority"),
                               ("category_breakdown", "Hiring by function")):
                breakdown = demand.get(key) or {}
                if isinstance(breakdown, dict) and breakdown:
                    rendered = ", ".join("%s %s" % (k, v)
                                         for k, v in sorted(breakdown.items()))
                    out.append("%s: %s" % (label, b.line(rendered, field=key,
                                                         dataset="job_openings")))
            return out

        docs.append(_build(account_id, index, "executive_dashboard",
                           "hiring_signal", "Hiring signal - %s" % company,
                           payload, fill_hiring))

    # -- events ---------------------------------------------------------------
    docs.extend(_signal_documents(db, account_id, index, company))

    # -- people ---------------------------------------------------------------
    influence = _widget(db, account_id, "stakeholder_influence_map")
    if influence:
        def fill_people(b):
            out = []
            coverage = influence.get("buying_group_coverage")
            if _text(coverage):
                out.append("Buying-group coverage: %s"
                           % b.line(coverage, field="buying_group_coverage",
                                    dataset="prospect_contacts"))
            breakdown = influence.get("influence_breakdown") or {}
            if isinstance(breakdown, dict) and breakdown:
                out.append("Stakeholders by influence type: %s"
                           % b.line(", ".join("%s %s" % (k, v) for k, v
                                              in sorted(breakdown.items())),
                                    field="influence_breakdown",
                                    dataset="prospect_contacts"))
            for i, group in enumerate((influence.get("department_groups") or [])
                                      [:MAX_DEPARTMENTS]):
                department = _text(group.get("department"))
                total = _text(group.get("total_count"))
                relevant = _text(group.get("hp_relevant_count"))
                if department and total:
                    out.append("%s department: %s contact(s) mapped, %s "
                               "HP-relevant." % (
                                   department,
                                   b.line(total, field="total_count",
                                          record_id=i,
                                          dataset="prospect_contacts"),
                                   relevant or "0"))
            entry = influence.get("ranked_entry_path")
            if isinstance(entry, list) and entry:
                names = [_text(e.get("department") if isinstance(e, dict) else e)
                         for e in entry[:5]]
                names = [n for n in names if n]
                if names:
                    out.append("Recommended entry path by department: %s"
                               % b.line(" then ".join(names),
                                        field="ranked_entry_path",
                                        dataset="prospect_contacts"))
            return out

        docs.append(_build(account_id, index, "executive_dashboard",
                           "stakeholders", "Stakeholders - %s" % company,
                           influence, fill_people))

    # -- technology -----------------------------------------------------------
    techmap = _widget(db, account_id, "technographic_map")
    if techmap:
        def fill_tech(b):
            out = []
            read = _text(techmap.get("strategic_read"))
            if read:
                out.append(b.line(read, field="strategic_read",
                                  dataset="technographics"))
            total = _text(techmap.get("total_detected_technologies"))
            if total:
                out.append("Technologies detected in use: %s"
                           % b.line(total, field="total_detected_technologies",
                                    dataset="technographics"))
            for i, cat in enumerate(techmap.get("categories") or []):
                name = _text(cat.get("category_name") or cat.get("name"))
                vendors = cat.get("vendors") or cat.get("technologies") or []
                rendered = ", ".join(_text(v.get("name") if isinstance(v, dict) else v)
                                     for v in vendors[:20] if v)
                if name and rendered:
                    out.append("%s technology in %s: %s"
                               % (company, name,
                                  b.line(rendered, field="category", record_id=i,
                                         dataset="technographics")))
            return out

        docs.append(_build(account_id, index, "executive_dashboard",
                           "technology", "Technology in place - %s" % company,
                           techmap, fill_tech))

    # -- intent ---------------------------------------------------------------
    intent = _widget(db, account_id, "intent_topics_table")
    topics = [t for t in (intent.get("topics") or [])
              if _text(t.get("topic_name"))][:MAX_INTENT_TOPICS]
    if topics:
        def fill_intent(b):
            out = ["Research topics showing intent at %s, strongest first."
                   % company]
            for i, topic in enumerate(topics):
                name = _text(topic.get("topic_name"))
                score = topic.get("composite_score")
                level = _text(topic.get("intent_level"))
                sentence = "%s (composite score %s%s)" % (
                    name, score, ", %s intent" % level if level else "")
                out.append(b.line(sentence, field="topic_name", record_id=i,
                                  dataset="intent_score",
                                  quote=name, value=score))
            return out

        docs.append(_build(account_id, index, "executive_dashboard",
                           "intent_topics", "Intent topics - %s" % company,
                           topics, fill_intent))

    # -- the filings ----------------------------------------------------------
    docs.extend(_filing_documents(account_id, index, company))

    return [d for d in docs if not d.is_empty()]


def _signal_documents(db, account_id, index, company) -> list:
    """Recent events, from the news feed and the opportunity triggers combined.

    Combined and de-duplicated on purpose. The two widgets overlap almost
    entirely - a trigger is a news signal that cleared a second bar - and ABX is
    explicit about what to do with that: *"If the same real-world event appears
    in News, Technology and Intent data, store it once as the same underlying
    event. Do not count the same event twice."* Indexing both would give the
    graph two witnesses to one dividend announcement.
    """
    feed = _widget(db, account_id, "news_signals_feed")
    triggers = _widget(db, account_id, "opportunity_trigger_signals")

    merged, seen = [], set()
    for row in list(feed.get("signals") or []) + list(triggers.get("triggers") or []):
        if not isinstance(row, dict):
            continue
        headline = _text(row.get("headline"))
        key = _text(row.get("signal_id")) or headline.lower()
        if not headline or key in seen:
            continue
        seen.add(key)
        merged.append(row)

    merged = merged[:MAX_SIGNALS]
    if not merged:
        return []

    def fill_signals(b):
        out = ["Recent events involving %s that a seller should know about."
               % company]
        for i, row in enumerate(merged):
            headline = _text(row.get("headline"))
            date = _text(row.get("event_date")) or _text(row.get("publication_date"))
            category = _text(row.get("category"))
            detail = "%s%s%s" % (
                headline,
                " (%s)" % date if date else "",
                " - category: %s" % category if category else "")
            out.append(b.line(detail, field="headline", record_id=i,
                              dataset=_text(row.get("dataset")) or "google_news",
                              publisher=_text(row.get("source_publisher")),
                              source_url=_text(row.get("source_url")),
                              quote=_text(row.get("raw_headline")) or headline,
                              period=date))
            evidence = _text(row.get("evidence_sentence"))
            if evidence:
                out.append("  Reported: %s"
                           % b.line(evidence, field="evidence_sentence",
                                    record_id=i,
                                    publisher=_text(row.get("source_publisher")),
                                    source_url=_text(row.get("source_url"))))
        return out

    return [_build(account_id, index, "executive_dashboard", "recent_signals",
                   "Recent signals - %s" % company, merged, fill_signals)]
