import logging
import re
from datetime import UTC, datetime

from bson import ObjectId

from app.config import scoring as _scoring
from app.database.mongodb import get_db
from app.observability import pipeline
from app.services.extractors.datasets import (
    account_display_name,
    read_dataset_records,
    requires_local_datasets,
)
from app.services.hp import (
    case_studies as cs,
    integration_routes as ir,
    rulebook as rb,
    tech_confidence as tconf,
)
from app.services.regen import store as widget_store

logger = logging.getLogger(__name__)

TECHNOGRAPHICS_CATEGORY_COLUMNS = [
    "Testing And Qa",
    "Sales",
    "Prog Langs And Frameworks",
    "Productivity And Operations",
    "Product And Design",
    "Platform And Storage",
    "Operations Software",
    "Operations Management",
    "Marketing",
    "It Security",
    "It Management",
    "Hr",
    "Finance And Accounting",
    "Ecommerce",
    "Devops And Development",
    "Customer Management",
    "Computer Networks",
    "Communications",
    "Collaboration",
    "Bi And Analytics"
]

# The export truncates every category cell: "Prog Langs And Frameworks" ends
# "... Google Cloud APIs (+16 more)". The marker is a count of what the vendor
# cut, not a technology, and it must never be rendered as one.
CATEGORY_TRUNCATION_MARKER = re.compile(r"\s*\(\+\s*\d+\s+more\s*\)\s*$", re.I)

# Where a technology named in Full Tech Stack reaches no category column. On
# the loaded accounts that is 95 of 281 and 294 of 589 - not a gap in the file
# but the other side of the truncation above, so the group says so rather than
# quietly dropping a third of the estate.
UNCATEGORISED_LABEL = "Not categorised in the export"
UNCATEGORISED_NOTE = ("the export truncates each category list, so these "
                      "technologies appear in Full Tech Stack with no category "
                      "of their own")


def _category_names(cell) -> list[str]:
    """The technologies named in one category cell, truncation marker removed."""
    out = []
    for item in str(cell or "").split(","):
        name = CATEGORY_TRUNCATION_MARKER.sub("", item).strip()
        if name and name not in out:
            out.append(name)
    return out


def multi_category_technologies(groups: list) -> int:
    """How many technologies the export files under more than one category."""
    seen: dict = {}
    for group in groups:
        for name in group["technologies"]:
            seen[name.lower()] = seen.get(name.lower(), 0) + 1
    return sum(1 for count in seen.values() if count > 1)


def category_groups(category_matrix: dict, full_tech_list: list) -> list[dict]:
    """The whole estate clubbed into the export's own categories.

    The client, 27 Sep: "we mention about 281 technologies detected - we need to
    club those in relevant categories and show here". The categories are the
    file's own 20 columns, which is also what the card footers already name, so
    nothing here is a taxonomy of ours.

    A technology may appear in several groups, because the export puts it in
    several columns: NetSuite is filed under BI, Sales, Finance, IT Management
    and Customer Management, all five. That is the file's own reading and it is
    not flattened here - so the group counts can sum to more than the number of
    distinct technologies, and `multi_category_technologies` says how many rows
    that affects rather than leaving a reader to wonder.

    Ordered largest first, then by name, with the uncategorised group last
    whatever its size. Ordering is settled here rather than in the browser.
    """
    groups = [{"category": name, "technologies": list(items), "count": len(items)}
              for name, items in category_matrix.items() if items]
    groups.sort(key=lambda g: (-g["count"], g["category"]))

    placed = {name.lower() for g in groups for name in g["technologies"]}
    rest = [name for name in full_tech_list if name.lower() not in placed]
    if rest:
        groups.append({"category": UNCATEGORISED_LABEL,
                       "technologies": rest,
                       "count": len(rest),
                       "note": UNCATEGORISED_NOTE})
    return groups

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

# ABX Feature 5 status vocabulary. Technographics is an install-base provider
# export, so a vendor it names is a Confirmed finding. Absence is Unknown and
# never "competitor absent" - the spec is explicit about that.
STATUS_CONFIRMED = "Confirmed"
STATUS_UNKNOWN = "Unknown"

# HP relationship, also from ABX Feature 5. Short label for the vendor chip,
# long form for the explanation - the long string was being rendered inside a
# badge, where it does not belong.
#
# The third value is the displacement risk shown on the vendor chip, using the
# reference application's vocabulary (High / Medium / Low): a confirmed
# competitor in an HP category is High, an unfilled category is Medium, a
# technology HP sits alongside is Low, and a category HP has no line in carries
# no risk rating at all.
RELATIONSHIP_BY_BADGE = {
    "displacement opportunity": (
        "Compete",
        "Compete - another vendor is confirmed in an HP-relevant category",
        "High risk"),
    "complementary attach": (
        "Complement",
        "Complement - HP can work alongside the confirmed technology",
        "Low risk"),
    "hp whitespace - open opportunity": (
        "Open opportunity",
        "Possible open opportunity - category need supported, no vendor confirmed",
        "Medium risk"),
    "contextual - no direct hp line": (
        "Contextual",
        "Contextual - no direct HP line in this category",
        None),
}


FULL_STACK_COLUMN = "Full Tech Stack"


def _derive_provenance(detected_as: list, techno_row: dict) -> str:
    """Name the columns a vendor is genuinely in.

    The provenance string used to be hardcoded per detection branch, so a card
    could assert a source it was never in: Symantec / Kaspersky claimed
    "IT SECURITY" and the ML frameworks claimed "PROG LANGS AND FRAMEWORKS"
    when both appear only in Full Tech Stack. Derived here instead, and using
    the dataset key `technographics` rather than the `4_Technographics` file
    label.
    """
    if not detected_as:
        return "technographics -> no matching entry"

    columns = []
    for column, value in (techno_row or {}).items():
        if column == FULL_STACK_COLUMN:
            continue
        haystack = str(value or "").lower()
        if any(str(d).lower() in haystack for d in detected_as):
            columns.append(column)

    if not columns:
        columns = [FULL_STACK_COLUMN]
    return "technographics -> " + ", ".join(sorted(columns)[:3])


def _normalise_hp_fields(categories: list, techno_row: dict | None = None) -> None:
    """Replace the placeholder scaffolding with real deterministic values.

    Every vendor row used to carry "Inferred TBD" for its risk level, a
    stubbed hp_play reading "TBD for future AI model execution", and a
    confidence of "TBD". Those were written before the inferred layer existed
    and rendered to sellers as though they were findings.

    What this layer can state deterministically it now states; what it cannot,
    it leaves absent for the recommendations widget to supply.
    """
    for category in categories:
        vendors = category.get("vendors") or []

        # A category whose only row is HP's own absence cannot be a Compete:
        # "Compete" means a rival is confirmed here, and none is. The badge was
        # set when the category was built, before the client-device filter
        # removed a firewall that was standing in for a laptop brand.
        confirmed_rivals = [v for v in vendors if not v.get("is_whitespace")]
        if vendors and not confirmed_rivals:
            category["status_badge"] = "HP whitespace - open opportunity"
            category["badge_type"] = "whitespace"

        badge = str(category.get("status_badge") or "").strip().lower()
        short, long, risk = RELATIONSHIP_BY_BADGE.get(badge, (None, None, None))

        # Narrative is filled in by the inferred layer, which writes it back
        # onto this structure after the HP rules and guardrails have run.
        category["what_it_means"] = None
        category["hp_relationship"] = long
        category["hp_relationship_label"] = short

        for vendor in category.get("vendors") or []:
            is_whitespace = bool(vendor.get("is_whitespace"))
            # What this value has always meant: whether the vendor string was
            # actually in the export, or arrived via a keyword rule. It is a
            # statement about DETECTION, and it used to be called `confidence`.
            #
            # `confidence` now carries the client's Tech Landscape score, which
            # answers a different question - whether the detected technology
            # supports the HP opportunity printed beside it. Both are worth
            # having, so the detection flag keeps its meaning under its own
            # name rather than being overwritten by a number.
            vendor["detection_status"] = (
                STATUS_UNKNOWN if is_whitespace else STATUS_CONFIRMED)
            # Cite the entries actually matched. A generic "named in the
            # technographics install-base export" was attached to cards whose
            # named product was not in the export at all - Microsoft Intune on
            # an Azure AD match, NVIDIA on a PyTorch match. Naming the real
            # entries makes any remaining mismatch visible on the card itself.
            detected_as = [d for d in (vendor.get("detected_as") or []) if d]
            if not is_whitespace:
                vendor["provenance"] = _derive_provenance(detected_as, techno_row)
            else:
                vendor["provenance"] = "technographics -> no vendor found for this category"
            if is_whitespace:
                vendor["evidence_basis"] = (
                    "no vendor for this category appears in the supplied "
                    "technographics export")
            elif detected_as:
                vendor["evidence_basis"] = "detected as %s in the technographics export" % (
                    ", ".join(detected_as[:4]))
            else:
                # Detected by a rule that did not record what it matched.
                # Without the matched entry the claim cannot be substantiated,
                # so it is Likely rather than Confirmed.
                vendor["detection_status"] = "Likely"
                vendor["evidence_basis"] = (
                    "matched a technographics keyword rule; the specific source "
                    "entry was not recorded")
            # Displacement risk for the chip; the relationship label and its
            # full ABX wording sit alongside it.
            #
            # A whitespace row is HP's own absence in the category, not a rival
            # to displace, so it always reads as an open opportunity even when
            # the category as a whole is a Compete. Inheriting the category's
            # risk labelled HP Inc. itself "High risk".
            if is_whitespace:
                vendor["risk_level"] = "Medium risk"
                vendor["hp_relationship_label"] = "Open opportunity"
                vendor["hp_relationship"] = RELATIONSHIP_BY_BADGE[
                    "hp whitespace - open opportunity"][1]
            else:
                vendor["risk_level"] = risk
                vendor["hp_relationship_label"] = short
                vendor["hp_relationship"] = long
            # Filled by the inferred layer with an HP line and a one-line play,
            # or left absent when no rule supports one.
            vendor["hp_play"] = None


# The HP line a card's play names, to the rulebook route Driver 1 scores
# against. Only the two service routes are derivable from an HP line: a card
# selling Wolf Security is asking a Wolf question, a Poly card a Poly question.
# The hardware lines do not name a service route, and a card with no play names
# nothing at all - both pass route=None, which asks the looser question "does
# any HP rule recognise this technology" and reports which rule answered.
#
# Guessing a route for the hardware lines would put a rule id on a card that the
# rulebook never connected to it.
# The Part B families each HP line may draw an offering from.
#
# Without this the Google Workspace card - whose HP line is Poly Collaboration
# - was given "WXP and WXP Collaboration" because WXP 08's terms include
# Google Workspace. Two different HP products on one card is the forced match
# C 07 forbids: "Where there is no clear relationship ... we should not force a
# match."
#
# An HP line absent from this map draws no offering, which is the safe
# direction: a card keeps the broad line it already had.
# The HP line each Part B family speaks for.
#
# All nine now, where before only four could: WXP, CARE, LIFE, DEPLOY and IQ
# named offerings the twelve-string list had no word for, so three rules that
# matched the Google Workspace card were discarded for want of somewhere to put
# the answer. Each name is the routing table's own opportunity type.
# Defined in `services/hp/rulebook.py`, which is where rulebook taxonomy
# belongs: the Objection Playbook needs the same mapping and should not have to
# import an unrelated extractor to get it. Re-exported here under its original
# name so every existing reference keeps working.
RULEBOOK_FAMILY_TO_HP_LINE = rb.RULEBOOK_FAMILY_TO_HP_LINE

HP_LINE_TO_RULEBOOK_FAMILIES = rb.HP_LINE_TO_RULEBOOK_FAMILIES


def _rulebook_offering(book: dict, vendor: dict, hp_line: str) -> dict | None:
    """The rulebook rule that speaks to this vendor's detected technology.

    Matched on the technology the account actually runs - "Kaspersky",
    "Symantec Endpoint Protection" - against the rules' own terms, so the
    offering named is the one HP wrote for that situation rather than the
    broad line a model picked from a list of six.

    Returns None whenever nothing matches, which is most cards: a network
    appliance or an OS has no HP offering, and C 07 says not to force one.
    """
    if not book.get("rules"):
        return None

    detected = [d for d in (vendor.get("detected_as") or []) if d]
    if not detected:
        detected = [vendor.get("vendor_name") or ""]
    evidence = [{"text": d} for d in detected if d]
    if not evidence:
        return None

    # Part B only. Part A chooses a hardware product, and that recommendation
    # is already made once per account by `recommendations.py`; repeating it on
    # every vendor card would say the same thing eight times.
    # Every Part B family is considered. Which line the card should carry is
    # then the rulebook's answer, not a filter on the model's.
    matches = [m for m in rb.candidates(book, evidence)
               if m["rule"].get("part") == "B"
               and m["family"] in RULEBOOK_FAMILY_TO_HP_LINE
               and not (m["modifier_only"] or m["routing_only"]
                        or m["catalogue_only"])]
    if not matches:
        return None

    match = matches[0]
    line = RULEBOOK_FAMILY_TO_HP_LINE[match["family"]]
    facts = rb.facts_for(match)
    return {
        "rule_label": match["rule_label"],
        "offering": match["offering"],
        # The line the rulebook says this card belongs to, and the one the
        # model had picked. They usually agree; where they do not, the
        # rulebook's is used and this records what changed.
        "hp_line": line,
        "model_line": hp_line or None,
        "line_changed": bool(hp_line and hp_line != line),
        "matched_terms": match["matched_terms"],
        # The rule's own sentences, with its prohibitions kept separate.
        "may_say": facts["allowed_facts"][:2],
        "must_not_say": facts["prohibitions"][:1],
    }


HP_PLAY_TO_ROUTE = {
    "hp wolf security": tconf.ROUTE_WOLF,
    "poly collaboration": tconf.ROUTE_POLY,
}


def _hp_category_intent(account_id: str) -> dict:
    """`{HP category: intent score}` for this account, or `{}`.

    Driver 2 reads the intent score for the card's own HP business category, and
    the document is emphatic that it must be that category's own score and no
    other. This returns the whole map so the caller picks per card rather than
    passing a category down and hoping.

    The `status == "matched"` gate is load-bearing: `_parse_category_file` finds
    the account's row by domain, and any other status means the scores in the
    file belong to somebody else. Returning `{}` then scores every card's
    Driver 2 as "missing", which is the bottom band - it weakens cards, and
    never suppresses one.
    """
    from app.services.extractors.datasets import account_domain, read_dataset_rows
    from app.services.extractors.intent_demand_signals import _parse_category_file

    try:
        parsed = _parse_category_file(
            read_dataset_rows(account_id, "hp_category_intent"),
            account_domain(account_id))
    except Exception:
        logger.exception("tech landscape: could not read hp_category_intent for %s",
                         account_id)
        return {}

    if parsed.get("status") != "matched":
        logger.info("tech landscape: hp_category_intent not matched for %s (%s) - "
                    "every card scores Driver 2 as missing",
                    account_id, parsed.get("status"))
        return {}

    return {name: entry.get("score")
            for name, entry in (parsed.get("categories") or {}).items()}


# Explorium 5_Tech_Breakdown columns in the order the Website stack card shows
# them: infrastructure a seller can talk about first, page metadata last. A
# column not listed here is still shown, after these, so a new vendor column is
# never dropped silently.
TECH_BREAKDOWN_ORDER = (
    "Cms", "Hosting", "Server", "Web Server", "Cdn", "Cdns", "Ns", "Mx", "Ssl",
    "Framework", "Javascript", "Analytics", "Ads", "Payment", "Ecommerce",
    "Mapping", "Widgets", "Media", "Mobile", "Language", "Feeds", "Link",
    "Web Master", "Docinfo", "Robots", "Copyright", "Seo Headers", "Seo Meta",
    "Seo Title",
)
# Columns that describe the page rather than a technology the company runs.
TECH_BREAKDOWN_PAGE_METADATA = frozenset({
    "Seo Headers", "Seo Meta", "Seo Title", "Copyright", "Docinfo", "Robots",
    "Language", "Feeds", "Link", "Web Master",
})
_TB_EMPTY = {"", "nan", "none", "null", "no data available", "-", "\u2014"}
_TB_ID_COLUMNS = {"business id", "company name", "company domain", "domain",
                  "status", "db indexed", "established", "parked", "umbrella"}


def _parse_tech_breakdown(records: list) -> list:
    """The tech_breakdown row, category by category, for the Website stack card.

    `"Enterprise: Adobe Experience Manager | Other: WordPress 5.3, Investis"`
    -> {"category": "Cms", "groups": [{"group": "Enterprise", "technologies":
    [...]}, ...], "technologies": [...]}, one per non-empty column.

    Copied as delivered: groups and names are the vendor's, only split and
    de-duplicated, so every item on the card can be found in the sheet.
    `_breakdown_technologies` below reads the same row as a flat list for the
    estate; this keeps the vendor's grouping for display.
    """
    if not records:
        return []
    row = {str(k).strip(): v for k, v in records[0].items()
           if str(k).strip().lower() not in _TB_ID_COLUMNS}
    columns = [c for c in TECH_BREAKDOWN_ORDER if c in row] + sorted(
        c for c in row if c not in TECH_BREAKDOWN_ORDER)
    out = []
    for column in columns:
        raw = " ".join(str(row.get(column) or "").split())
        if raw.lower() in _TB_EMPTY:
            continue
        groups, flat = [], []
        for part in raw.split("|"):
            part = part.strip()
            if not part:
                continue
            group, sep, rest = part.partition(":")
            if not sep:
                group, rest = "", part
            names = []
            for name in rest.split(","):
                name = name.strip()
                if name and name not in names:
                    names.append(name)
            if names:
                groups.append({"group": group.strip(), "technologies": names})
                flat.extend(n for n in names if n not in flat)
        if flat:
            out.append({"category": column, "groups": groups, "technologies": flat,
                        "page_metadata": column in TECH_BREAKDOWN_PAGE_METADATA})
    return out


def _hp_category_file(account_id: str) -> dict:
    """The parsed HP category intent file for this account, or `{}`.

    `detected_technologies` reads Related Technologies out of
    `category_file["categories"]`. `_hp_category_intent` returns only the
    {category: score} map, so passing that meant no Related Technology was ever
    added. Same `status == "matched"` gate: any other status means the row
    belongs to somebody else.
    """
    from app.services.extractors.datasets import account_domain, read_dataset_rows
    from app.services.extractors.intent_demand_signals import _parse_category_file

    try:
        parsed = _parse_category_file(
            read_dataset_rows(account_id, "hp_category_intent"),
            account_domain(account_id))
    except Exception:
        logger.exception("tech landscape: could not read hp_category_intent for %s",
                         account_id)
        return {}
    return parsed if parsed.get("status") == "matched" else {}


# --------------------------------------------------------------------------
# What counts as a technology this account has
# --------------------------------------------------------------------------
# Four sheets carry technology, and the client named all four (Dhruvi, 27 Sep):
# "Technographics: please also refer to the WebStack and Tech_Breakdown sheets
# in Explorium. And Related Technologies column in hp_intent_results" - for
# accounts where Technographics is thin or absent. It is absent on 13 of the
# 220, where the Technographic Map showed nothing at all.
#
# They are not the same kind of evidence, and reading what is actually in them
# settles how they may be used:
#
#   Technographics       the installed estate. 589 entries for Accenture.
#   Related Technologies the client's own intent file naming the technology
#                        behind a category it scored - HP-relevant by
#                        construction, and the client asserting the account
#                        has it.
#   WebStack             what runs on the company's WEBSITE: AWS Cloudfront
#                        edge nodes, Akamai DNS, ASP.NET, cookie banners. 429
#                        entries for Astra, not one of them an installed
#                        product.
#   Tech_Breakdown       the same website technology, grouped into columns
#                        (Hosting, Cdns, Analytics, Widgets, Ads).
#
# So the first two are pooled as the estate, and the website sheets are read
# only when the estate has nothing - the client's "or not there" case. Pooling
# all four always would have taken Astra from 220 detected technologies to 649
# and let an HP category card rest on a CDN edge node. Either way every
# technology keeps the sheet it came from, so a card built on website evidence
# can say that is what it is.
SOURCE_TECHNOGRAPHICS = "technographics"      # the installed estate
SOURCE_INTENT_RELATED = "hp_category_intent"  # the client's own intent file
SOURCE_WEBSTACK = "webstack"                  # website technology
SOURCE_TECH_BREAKDOWN = "tech_breakdown"      # website technology, grouped

# Columns of Tech_Breakdown that are not technology names.
BREAKDOWN_SKIP_COLUMNS = {"business id", "status", "db indexed", "established",
                          "parked", "umbrella", "docinfo", "seo meta",
                          "seo headers", "seo title", "language", "mobile"}


def _split_list(value) -> list:
    """A comma-separated cell into its entries, blanks dropped."""
    text = str(value or "").strip()
    if not text or text.lower() in ("nan", "none", "null"):
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _breakdown_technologies(rows) -> list:
    """Every technology named in Tech_Breakdown, column by column.

    A cell reads "Other: Akamai Hosted, U.S. Server Location" - a vendor
    grouping, a colon, then the technologies. The grouping labels the entries
    rather than naming one, so it is dropped.
    """
    out = []
    for row in rows or []:
        for column, value in (row or {}).items():
            if not value or str(column or "").strip().lower() in BREAKDOWN_SKIP_COLUMNS:
                continue
            cell = str(value)
            if ":" in cell:
                cell = cell.split(":", 1)[1]
            out.extend(_split_list(cell))
    return out


def detected_technologies(techno_records, webstack_records, breakdown_records,
                          category_file) -> tuple[list, dict, dict]:
    """(technology names, name -> the sheet that named it, how it was sourced).

    Deduplicated case-insensitively, first sheet wins, order preserved so the
    installed estate still reads first on every card.
    """
    seen: dict[str, str] = {}
    names: list[str] = []

    def add(raw, source):
        for entry in raw:
            key = str(entry).strip().lower()
            if not key or key in seen:
                continue
            seen[key] = source
            names.append(str(entry).strip())

    for row in (techno_records or [])[:1]:
        add(_split_list(row.get("Full Tech Stack")), SOURCE_TECHNOGRAPHICS)
    # Whether the website sheets are needed is decided on Technographics alone.
    # The intent file's Related Technologies is a welcome addition but a thin
    # one - Toyota has exactly one entry, "Fastly" - and letting it stand in for
    # an estate would leave that account with a one-technology map while nine
    # more sat unread in WebStack.
    estate_count = len(names)
    for entry in (category_file or {}).get("categories", {}).values():
        add([t for t in (entry.get("related_technologies") or []) if str(t).strip()],
            SOURCE_INTENT_RELATED)

    if not estate_count:
        # Nothing about the estate. The website sheets are what the client told
        # us to read here, and they beat an empty card - as long as the card
        # says what it is resting on.
        for row in (webstack_records or [])[:1]:
            add(_split_list(row.get("Technologies Used By Company Website")),
                SOURCE_WEBSTACK)
        add(_breakdown_technologies(breakdown_records), SOURCE_TECH_BREAKDOWN)

    website_count = sum(1 for src in seen.values() if src in
                        (SOURCE_WEBSTACK, SOURCE_TECH_BREAKDOWN))
    meta = {
        "estate_technologies": estate_count,
        "website_technologies": website_count,
        "website_sources_used": bool(website_count),
        "basis": "installed estate" if estate_count else (
            "website technology only - no Technographics row for this account"
            if names else "no technology detected in any source"),
    }
    return names, seen, meta


def _source_counts(tech_sources: dict) -> dict:
    """How many technologies each sheet contributed, for the run log."""
    counts: dict[str, int] = {}
    for source in (tech_sources or {}).values():
        counts[source] = counts.get(source, 0) + 1
    return counts


def _score_card_confidence(categories: list, intent_scores: dict) -> dict:
    """Attach the client's Tech Landscape confidence to every vendor card.

    Runs AFTER `generate_map_narrative`, because Driver 1 is scored against the
    HP opportunity on the card and `hp_play` is not populated until the
    narrative layer has run. Scoring earlier would ask the question with the
    answer missing.

    Returns a report: how many cards were scored, and which were suppressed by
    the document's guardrail. The suppression count is published rather than
    silent - a card vanishing from a seller's screen should be explicable.
    """
    # Read once for the whole pass. The rulebook is 166 documents, and a card
    # asking for it per vendor would re-read it eight times for one account.
    try:
        book = rb.load(get_db())
    except Exception:
        logger.exception("tech landscape: rulebook unavailable for card offerings")
        book = {"rules": []}

    report = {"scored": 0, "suppressed": [], "formula": tconf.FORMULA,
              "formula_authority": tconf.FORMULA_AUTHORITY,
              "intent_scores_available": bool(intent_scores),
              # See the note in urgency.py - this is what lets a weight change
              # in config/scoring.yaml reach the cards.
              "scoring_config_version": _scoring.version("tech_confidence")}

    for category in categories or []:
        hp_category = tconf.hp_category_for(category.get("category_key") or "")
        intent = intent_scores.get(hp_category) if hp_category else None
        d2, d2_basis = tconf.driver_2_intent(intent, hp_category)

        kept = []
        for vendor in category.get("vendors") or []:
            # A whitespace row is HP's own ABSENCE from a category - "no vendor
            # confirmed here". It makes no technology claim, so Driver 1 has
            # nothing to evaluate and the document's guardrail does not reach
            # it: the guardrail suppresses a card whose technology evidence does
            # not support its opportunity, and this card's point is that there
            # is no technology to support.
            #
            # Scoring it anyway gave every whitespace row 0 and deleted it,
            # which removed exactly the cards a seller most wants - the open
            # opportunities. It carries no confidence rather than a false one.
            if vendor.get("is_whitespace"):
                vendor["confidence"] = None
                vendor["confidence_drivers"] = {
                    "not_scored": "HP's absence from this category is not a "
                                  "technology detection, so the Tech Landscape "
                                  "confidence does not apply to it",
                }
                kept.append(vendor)
                continue

            play = vendor.get("hp_play") or {}
            product = str(play.get("product") or "").strip()

            # The rulebook decides the line where it has a rule for what was
            # detected here; the model's pick stands where it does not. The
            # line is settled BEFORE the route is read, so a correction reaches
            # the score - the formula is untouched, its input is better.
            offering = _rulebook_offering(book, vendor, product)
            if offering:
                vendor["rulebook_offering"] = offering
                product = offering["hp_line"]
                play["product"] = product

            # What stands behind the line on this card. A rulebook match is an
            # authorised answer; anything else is the model positioning a broad
            # line against a detected vendor, which is reasonable but is not a
            # rule. A seller deciding what to say to a customer should be able
            # to tell the two apart without opening the code.
            play["product_source"] = "rulebook" if offering else "positioning"
            if product:
                vendor["hp_play"] = play

            route = HP_PLAY_TO_ROUTE.get(product.lower())

            # The HP opportunity this card is actually making. The play names it
            # when the narrative layer found one; otherwise the category's own
            # HP business line does. A category with neither - one the platform
            # itself badges "no direct HP line" - offers nothing for a
            # technology to be related TO, which is the document's 0.
            hp_opportunity = product or hp_category

            detected = [d for d in (vendor.get("detected_as") or []) if d]
            if not detected:
                detected = [vendor.get("vendor_name") or ""]

            d1, d1_basis, matched = tconf.driver_1_for_card(
                detected, route, hp_opportunity)

            vendor["confidence"] = tconf.confidence(d1, d2)
            vendor["confidence_drivers"] = {
                "technology_evidence": {"score": d1, "weight": tconf.DRIVER_1_WEIGHT,
                                        "basis": d1_basis, "matched_rule": matched},
                "intent_support": {"score": d2, "weight": tconf.DRIVER_2_WEIGHT,
                                   "basis": d2_basis, "hp_category": hp_category},
            }

            if tconf.is_publishable(d1):
                report["scored"] += 1
                kept.append(vendor)
            else:
                report["suppressed"].append({
                    "category": category.get("category_key"),
                    "vendor": vendor.get("vendor_name"),
                    "reason": d1_basis,
                })

        category["vendors"] = kept

    return report


@requires_local_datasets(
    "technographics", "technology_detections", "webstack",
)
@pipeline.feature("tech_landscape")
def extract_tech_landscape(account_id: str,  # noqa: PLR0912, PLR0915 - branch-heavy extractor predates the lint gate
                           parts=("core", "recs")) -> list[dict]:
    """Tech Landscape. `parts` selects what is published: the regeneration
    engine runs the four deterministic widgets ("core") and the HP
    recommendations ("recs") as two producers, because the recommendations read
    outputs - the executive summary, trigger signals - that sit downstream of
    the tech stack."""
    db = get_db()
    now = datetime.now(UTC)

    # Get dynamic account name
    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})

    account_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"

    # Try firmographics for exact company_name if present
    firmo_records = _read_dataset_records(account_id, "firmographics")
    if firmo_records and len(firmo_records) > 0:
        f_name = account_display_name(account_id, firmo_records[0])
        if f_name:
            account_name = f_name

    techno_records = _read_dataset_records(account_id, "technographics")
    detection_records = _read_dataset_records(account_id, "technology_detections")
    webstack_records = _read_dataset_records(account_id, "webstack")

    pipeline.step("datasets", "", firmographics=len(firmo_records or []),
                  technographics=len(techno_records or []),
                  detections=len(detection_records or []),
                  webstack=len(webstack_records or []))

    results = []

    breakdown_records = _read_dataset_records(account_id, "tech_breakdown")
    full_tech_list, tech_sources, tech_basis = detected_technologies(
        techno_records, webstack_records, breakdown_records,
        _hp_category_file(account_id))
    pipeline.step("technology", "%d detected (%s)"
                  % (len(full_tech_list), tech_basis["basis"]),
                  **_source_counts(tech_sources))
    if tech_basis["website_sources_used"]:
        logger.info("tech landscape: %s has no Technographics row - the map is "
                    "built from website technology, as the client directed on "
                    "27 Sep", account_id)

    full_tech_lower = [t.lower() for t in full_tech_list]

    def _kw_in(kw: str, entry: str) -> bool:
        """Word-boundary match.

        Plain substring matching put "Adobe Digital Marketing Suite" under
        Google Workspace, because "g suite" is inside "marketin(g suite)".
        The same failure mode was fixed in the Opportunity Map and the
        Objection Playbook; this is the last copy of it.
        """
        return re.search(r"(?<![a-z0-9])" + re.escape(kw.lower()) + r"(?![a-z0-9])",
                         entry) is not None

    # Entries that name network, server or storage equipment are not client
    # devices, whatever brand is on them. "Huawei Firewall" was driving the
    # PC/Laptop Brands card - and with it a Compete rating and an HP Elite/Pro
    # PC recommendation - on the strength of a firewall.
    NON_CLIENT_TERMS = ("firewall", "router", "switch", "server", "storage",
                        "san", "nas", "gateway", "access point", "load balancer")

    def _is_client_device(entry: str) -> bool:
        return not any(term in entry for term in NON_CLIENT_TERMS)

    def has_tech(*kw_list):
        return any(any(_kw_in(kw, t) for kw in kw_list) for t in full_tech_lower)

    def has_client_tech(*kw_list):
        """A brand match that is actually a client device."""
        return any(any(_kw_in(kw, t) for kw in kw_list) and _is_client_device(t)
                   for t in full_tech_lower)

    def matched_client_tech(*kw_list):
        return [orig for orig, low in zip(full_tech_list, full_tech_lower)
                if any(_kw_in(kw, low) for kw in kw_list) and _is_client_device(low)]

    def matched_tech(*kw_list):
        """The actual stack entries that matched, not just whether one did.

        A card that names "Microsoft Intune" while the stack only contains
        "Microsoft Azure AD MFA" is asserting a product the account does not
        have. Carrying the matched entries lets every card state what was
        really found, and makes a mismatch visible instead of silent.
        """
        out = []
        for original, lowered in zip(full_tech_list, full_tech_lower):
            if any(_kw_in(kw, lowered) for kw in kw_list):
                out.append(original)
        return out

    # 1. Widget: technographic_map (HP Strategic Technographic Map)
    hp_categories = []

    # Category 1: Client OS
    client_os_vendors = []
    if has_tech("windows", "microsoft windows"):
        client_os_vendors.append({
            "vendor_name": "Microsoft",
            "detected_as": matched_tech("windows", "microsoft windows"),
            "description": "Microsoft Windows platform",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP sales play mapping is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("apple", "macos", "ios"):
        client_os_vendors.append({
            "vendor_name": "Apple",
            "detected_as": matched_tech("apple", "macos", "ios"),
            "description": "Apple platform",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP sales play mapping is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("linux", "centos", "unix"):
        client_os_vendors.append({
            "vendor_name": "Linux / Enterprise OS",
            "detected_as": matched_tech("linux", "centos", "unix"),
            "description": "Linux / Unix platform",
            "risk_level": "Inferred TBD",
            "hp_play": None,
            "confidence": "TBD"
        })

    if client_os_vendors:
        hp_categories.append({
            "category_key": "client_os",
            "category_name": "Client OS",
            "detected_signals_count": len(client_os_vendors),
            "whitespace_count": 0,
            "status_badge": "Contextual - no direct HP line",
            "badge_type": "contextual",
            "is_opportunity": False,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - Strategic narrative synthesis for Client OS is TBD for future AI model generation ]",
            "vendors": client_os_vendors
        })

    # Category 2: PC/Laptop Brands
    pc_vendors = []
    if has_client_tech("dell"):
        pc_vendors.append({
            "vendor_name": "Dell (SAN)",
            "detected_as": matched_client_tech("dell"),
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_client_tech("huawei"):
        pc_vendors.append({
            "vendor_name": "Huawei",
            "detected_as": matched_client_tech("huawei"),
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_client_tech("lenovo"):
        pc_vendors.append({
            "vendor_name": "Lenovo",
            "detected_as": matched_client_tech("lenovo"),
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP hardware displacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_client_tech("msi"):
        pc_vendors.append({
            "vendor_name": "MSI",
            "detected_as": matched_client_tech("msi"),
            "description": "Enterprise laptops/desktops (incumbent)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP workstation displacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    has_hp_pc = has_tech("hp inc", "hewlett packard", "elitebook", "probook")
    whitespace_pc_count = 0
    if not has_hp_pc:
        whitespace_pc_count = 1
        pc_vendors.append({
            "vendor_name": "HP Inc.",
            "description": f"No HP client hardware detected in current {account_name} fleet",
            "is_whitespace": True,
            "risk_level": "HP whitespace - open opportunity",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "PC fleet consolidation play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    hp_categories.append({
        "category_key": "pc_laptop_brands",
        "category_name": "PC/Laptop Brands",
        "detected_signals_count": len(pc_vendors) - whitespace_pc_count,
        "whitespace_count": whitespace_pc_count,
        "status_badge": "Displacement opportunity",
        "badge_type": "displacement",
        "is_opportunity": True,
        "what_it_means": "[ HP Sales Angle: Inferred TBD - Strategic PC consolidation narrative synthesis is TBD for future AI model generation ]",
        "vendors": pc_vendors
    })

    # Category 3: UEM/MDM
    uem_vendors = []
    if has_tech("jamf"):
        uem_vendors.append({
            "vendor_name": "Jamf",
            "detected_as": matched_tech("jamf"),
            "description": "Apple device management",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "UEM attach play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    # Intune only. "azure ad" used to match here, so a stack containing only
    # "Microsoft Azure AD MFA" produced a card claiming Microsoft Intune and
    # "Windows device management". Azure AD authenticates people; it does not
    # manage a device estate - the same rule the Objection Playbook already
    # enforces, where identity is context for endpoint security rather than
    # evidence of device management.
    if has_tech("intune"):
        uem_vendors.append({
            "vendor_name": "Microsoft Intune",
            "description": "Windows device management",
            "detected_as": matched_tech("intune"),
        })
    # Workspace ONE / AirWatch only. Bare "vmware" matched plain "VMware",
    # which is virtualization, not unified endpoint management.
    if has_tech("workspace one", "airwatch"):
        uem_vendors.append({
            "vendor_name": "VMware Workspace ONE / AirWatch",
            "description": "Cross-platform UEM",
            "detected_as": matched_tech("workspace one", "airwatch"),
        })

    if uem_vendors:
        hp_categories.append({
            "category_key": "uem_mdm",
            "category_name": "UEM/MDM",
            "detected_signals_count": len(uem_vendors),
            "whitespace_count": 0,
            "status_badge": "Complementary attach",
            "badge_type": "complementary",
            "is_opportunity": True,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - Strategic UEM/MDM attach narrative synthesis is TBD for future AI model generation ]",
            "vendors": uem_vendors
        })

    # Category 4: Workstations & High-Performance Compute
    workstation_vendors = []
    # Split, because these are two different findings that were sharing one
    # card. "pytorch", "keras" and "spark" used to produce a card headed
    # "NVIDIA CUDA / GPUs - Graphics & AI compute infrastructure" on a stack
    # containing PyTorch, Keras and Apache Spark MLlib and no NVIDIA at all.
    # An ML framework is a software signal; it is not evidence of GPU hardware.
    if has_tech("nvidia", "cuda"):
        workstation_vendors.append({
            "vendor_name": "NVIDIA CUDA / GPUs",
            "description": "Graphics & AI compute infrastructure",
            "detected_as": matched_tech("nvidia", "cuda"),
        })
    if has_tech("pytorch", "keras", "tensorflow", "spark mllib"):
        workstation_vendors.append({
            "vendor_name": "AI / ML frameworks",
            "description": "Machine-learning software in use; does not by itself "
                           "evidence GPU or workstation hardware",
            "detected_as": matched_tech("pytorch", "keras", "tensorflow", "spark mllib"),
        })
    if has_tech("autocad", "autodesk", "catia", "solidworks", "blender"):
        workstation_vendors.append({
            "vendor_name": "AutoCAD / Autodesk",
            "detected_as": matched_tech("autocad", "autodesk", "catia", "solidworks", "blender"),
            "description": "Computer-aided design & 3D rendering",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "ZBook Workstation CAD play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    if workstation_vendors:
        hp_categories.append({
            "category_key": "workstations_compute",
            "category_name": "Workstations & High-Performance Compute",
            "detected_signals_count": len(workstation_vendors),
            "whitespace_count": 0,
            "status_badge": "Displacement opportunity",
            "badge_type": "displacement",
            "is_opportunity": True,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - High-performance compute narrative synthesis is TBD for future AI model generation ]",
            "vendors": workstation_vendors
        })

    # Category 5: IT Security & Endpoint Protection
    security_vendors = []
    if has_tech("aruba clearpass", "aruba networks"):
        security_vendors.append({
            "vendor_name": "Aruba ClearPass",
            "detected_as": matched_tech("aruba clearpass", "aruba networks"),
            "description": "Network access control (NAC)",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security attachment play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("cloudflare"):
        security_vendors.append({
            "vendor_name": "Cloudflare",
            "detected_as": matched_tech("cloudflare"),
            "description": "Edge & DNS security",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security containment play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("kaspersky", "symantec"):
        security_vendors.append({
            "vendor_name": "Symantec / Kaspersky",
            "detected_as": matched_tech("kaspersky", "symantec"),
            "description": "Traditional endpoint antivirus",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Wolf Security replacement play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    if security_vendors:
        hp_categories.append({
            "category_key": "it_security_parity",
            "category_name": "IT Security & Endpoint Protection",
            "detected_signals_count": len(security_vendors),
            "whitespace_count": 0,
            "status_badge": "Complementary attach",
            "badge_type": "complementary",
            "is_opportunity": True,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - Endpoint security narrative synthesis is TBD for future AI model generation ]",
            "vendors": security_vendors
        })

    # Category 6: Collaboration & Hybrid Workplace
    collab_vendors = []
    if has_tech("google workspace", "g suite", "google sheets"):
        collab_vendors.append({
            "vendor_name": "Google Workspace",
            "detected_as": matched_tech("google workspace", "g suite", "google sheets"),
            "description": "Cloud productivity suite",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "Poly audio/video room attach play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })
    if has_tech("atlassian cloud", "jira software", "confluence"):
        collab_vendors.append({
            "vendor_name": "Atlassian Cloud",
            "detected_as": matched_tech("atlassian cloud", "jira software", "confluence"),
            "description": "Developer collaboration & JIRA",
            "risk_level": "Inferred TBD",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "Developer endpoint play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    if collab_vendors:
        hp_categories.append({
            "category_key": "collaboration_hybrid",
            "category_name": "Collaboration & Hybrid Workplace",
            "detected_signals_count": len(collab_vendors),
            "whitespace_count": 0,
            "status_badge": "Complementary attach",
            "badge_type": "complementary",
            "is_opportunity": True,
            "what_it_means": "[ HP Sales Angle: Inferred TBD - Hybrid collaboration narrative synthesis is TBD for future AI model generation ]",
            "vendors": collab_vendors
        })

    # Category 7: Print Fleet & Document Infrastructure
    has_hp_print = has_tech("hp print", "managed print", "laserjet")
    whitespace_print_count = 0
    print_vendors = []
    if not has_hp_print:
        whitespace_print_count = 1
        print_vendors.append({
            "vendor_name": "HP Inc. Print",
            "description": f"No dedicated print hardware detected in current {account_name} fleet",
            "is_whitespace": True,
            "risk_level": "HP whitespace - open opportunity",
            "hp_play": {
                "product": "Inferred TBD",
                "play_text": "HP Managed Print Services play is TBD for future AI model execution."
            },
            "confidence": "TBD"
        })

    hp_categories.append({
        "category_key": "print_fleet",
        "category_name": "Print Fleet & Document Infrastructure",
        "detected_signals_count": len(print_vendors) - whitespace_print_count,
        "whitespace_count": whitespace_print_count,
        "status_badge": "HP whitespace - open opportunity",
        "badge_type": "whitespace",
        "is_opportunity": True,
        "what_it_means": "[ HP Sales Angle: Inferred TBD - Print fleet optimization narrative synthesis is TBD for future AI model generation ]",
        "vendors": print_vendors
    })

    # Narrative and HP plays are no longer stubbed here. This widget is the
    # deterministic layer: it reports what was detected and what HP relationship
    # follows from that. The sales narrative and the product recommendation come
    # from technographic_hp_recommendations, which is grounded in the HP decks
    # and filtered for this account's market. A placeholder saying "TBD for
    # future AI model generation" is worse than an absent field - it renders as
    # content.
    _normalise_hp_fields(
        hp_categories,
        techno_row=(techno_records[0] if techno_records else {}),
    )

    # Fill the narrative the seller actually reads: one line per category on
    # what it means for HP, and an HP line plus a one-line play per detected
    # vendor. Generated, but bounded - the HP line must resolve to the approved
    # product enum, and a positioning sentence may not carry a specification.
    narrative_report = {"generated": 0, "rejected": [], "prompt_version": None}
    try:
        from app.services.hp.map_narrative import generate_map_narrative
        narrative_report = generate_map_narrative(
            hp_categories,
            account_texts=[*full_tech_list, account_name],
            account_name=account_name,
        )
    except Exception:
        logger.exception("tech landscape: map narrative generation failed for %s",
                         account_id)

    # The client's Tech Landscape confidence. Last, because Driver 1 scores the
    # technology against the HP opportunity on the card, and `hp_play` only
    # exists once the narrative layer above has run.
    confidence_report = _score_card_confidence(hp_categories,
                                               _hp_category_intent(account_id))
    if confidence_report["suppressed"]:
        logger.info("tech landscape: %d card(s) suppressed for %s - no HP "
                    "rulebook rule supports the detected technology",
                    len(confidence_report["suppressed"]), account_id)
        pipeline.guardrail(len(confidence_report["suppressed"]),
                           "no rulebook rule supports the detected technology")

    strategic_read_text = narrative_report.get("strategic_read")

    # No hardcoded fallback: an account with no technographics has zero detected
    # technologies, not the count that happened to suit one account.
    detected_tech_count = len(full_tech_list)

    # Two different things that were sharing one number. "HP-mapped" is what the
    # label claims: categories where at least one vendor resolved to an HP line.
    # The opportunity count is a separate idea and now has its own field. They
    # happened to be equal on the first account, which hid the mistake.
    hp_line_categories = len([
        c for c in hp_categories
        if any(v.get("hp_play") for v in (c.get("vendors") or []))
    ])
    mapped_count = len([c for c in hp_categories if c["is_opportunity"]])
    whitespace_cat_count = len([c for c in hp_categories if c["whitespace_count"] > 0])

    pipeline.step("categories", "", detected_tech=detected_tech_count,
                  categories=len(hp_categories), hp_mapped=hp_line_categories,
                  opportunity=mapped_count, whitespace=whitespace_cat_count)

    # The header total and the per-category counts answer different questions:
    # `detected_tech_count` is every entry in the technographics export, while
    # the cards below only count vendors a rule matched into the 7 HP
    # categories. They are not meant to be equal, and on this account they
    # differ by an order of magnitude (220 vs ~20). Publishing the mapped total
    # alongside it lets the UI state the relationship instead of leaving a
    # reader to assume the cards account for all 220.
    mapped_signal_count = sum(c["detected_signals_count"] for c in hp_categories)

    # F9: a case study may strengthen "what it means for HP" on a category,
    # and nowhere else on this widget. The Technographic Map picks last of all
    # the surfaces, so a category carries proof only where nothing that needs
    # it more has already taken the study.
    try:
        _taken = cs.cited_above(db, account_id, cs.SURFACE_TECHMAP)
        _here: set = set()
        # Industry comes from the account's own firmographics, the same
        # source every other surface uses for the case-study industry match.
        _firmo = (_read_dataset_records(account_id, "firmographics") or [{}])[0]
        _industry = cs.normalise_industry(
            _firmo.get("Linkedin Industry Category")
            or _firmo.get("Naics Description") or "")
        for _cat in hp_categories:
            if not str(_cat.get("what_it_means") or "").strip():
                continue
            _lines: list = []
            for _v in _cat.get("vendors") or []:
                _prod = str(((_v.get("hp_play") or {}).get("product")) or "").strip()
                for _ln in cs.lines_for_product_text(_prod):
                    if _ln not in _lines:
                        _lines.append(_ln)
            if not _lines:
                continue
            _point = cs.allocate(db, _lines, industry=_industry,
                                 signals=cs.signals_for_opportunity(
                                     _cat.get("category_name")),
                                 taken=_taken, used_here=_here)
            if _point:
                _cat["hp_proof_point"] = _point
                if _point.get("study_id"):
                    _here.add(_point["study_id"])
    except Exception:
        logger.exception("tech landscape: proof allocation failed for %s", account_id)

    # Integration routes, as context only. Built from the full detected list
    # rather than the mapped cards, because a technology HP names as a target
    # is worth pointing out even when it did not land in an HP category.
    try:
        _book = rb.load(get_db())
        integration_lines = ir.routes_for(
            full_tech_list, (_book or {}).get("rules") or [])
    except Exception:
        logger.exception("tech landscape: integration routes failed for %s", account_id)
        integration_lines = []

    techno_map_payload = {
        "account_id": account_id,
        "feature_key": "tech_landscape",
        "widget_key": "technographic_map",
        "data_classification": "deterministic",
        "status": "available",
        "data": {
            "strategic_read": strategic_read_text,
            "total_detected_technologies": detected_tech_count,
            # Detected technology is no longer one sheet. Technographics is the
            # installed estate; the other three are what the client told us to
            # read where it is thin (27 Sep). The split is published so a card
            # resting on a website technology can be told from one resting on
            # an installed product.
            "technology_source_counts": _source_counts(tech_sources),
            "technology_basis": tech_basis,
            # Sum of the per-category "N detected signals" lines, so the UI can
            # show coverage rather than implying the cards cover the full stack.
            "mapped_signal_count": mapped_signal_count,
            "total_categories": len(hp_categories),
            "hp_mapped_categories": f"{hp_line_categories}/{len(hp_categories)}",
            "opportunity_categories": f"{mapped_count}/{len(hp_categories)}",
            "whitespace_categories": f"{whitespace_cat_count}/{len(hp_categories)}",
            # The 7 categories are a fixed HP taxonomy defined in this module,
            # not a count discovered in the account's data. Stated so the UI can
            # say so rather than implying the account has exactly 7 categories.
            "categories_are_fixed_taxonomy": True,
            "categories": hp_categories,
            # Client direction, 24 Sep: where a detected technology is one HP
            # names as an integration target, say so as CONTEXT - "Intune
            # detected; possible WXP integration route" - and never let it
            # become a recommendation on its own. Technology presence shows
            # compatibility, not need.
            "integration_routes": integration_lines,
            # The category/vendor narrative inside `categories` is generated;
            # everything else in this widget is computed. Recorded so the
            # classification stays honest even though both live here.
            "narrative_source": "inferred",
            "narrative_report": narrative_report,
            "confidence_report": confidence_report
        },
        # hp_category_intent feeds Driver 2 of the card confidence. It is NOT in
        # `requires_local_datasets` on purpose: the client's document puts a
        # missing intent score in the bottom band rather than treating it as an
        # error, so an account without the file still gets a Tech Landscape -
        # every card simply scores Driver 2 = 0.
        "source_datasets": ["technographics", "technology_detections", "webstack",
                            "tech_breakdown", "hp_category_intent"],
        "extracted_at": now,
        "updated_at": now
    }

    widget_store.put(account_id, "technographic_map", techno_map_payload, db=db)
    results.append(techno_map_payload)

    # 2. Widget: tech_stack_matrix (Raw 19 Category Matrix)
    category_matrix = {}
    if techno_records and len(techno_records) > 0:
        row = techno_records[0]
        for col in TECHNOGRAPHICS_CATEGORY_COLUMNS:
            items = _category_names(row.get(col))
            if items:
                category_matrix[col] = items

    groups = category_groups(category_matrix, full_tech_list)

    if full_tech_list or category_matrix:
        matrix_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "tech_stack_matrix",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_tech_count": len(full_tech_list),
                "full_tech_stack": full_tech_list,
                # Which sheet named each technology. Software installed across
                # an estate and a script on the company's website are not the
                # same claim, so a reader can tell them apart rather than
                # taking one list on trust.
                "technology_sources": tech_sources,
                "technology_source_counts": _source_counts(tech_sources),
                "technology_basis": tech_basis,
                "category_matrix": category_matrix,
                "categories_count": len(category_matrix),
                # The same technologies, clubbed and ordered for a reader, with
                # everything the export left uncategorised in a group of its
                # own so the groups add up to total_tech_count.
                "category_groups": groups,
                "uncategorised_count": next(
                    (g["count"] for g in groups
                     if g["category"] == UNCATEGORISED_LABEL), 0),
                "multi_category_technologies": multi_category_technologies(groups),
            },
            "source_datasets": ["technographics", "webstack", "tech_breakdown",
                                "hp_category_intent"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        matrix_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "tech_stack_matrix",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["technographics"],
            "extracted_at": now,
            "updated_at": now
        }

    widget_store.put(account_id, "tech_stack_matrix", matrix_payload, db=db)
    results.append(matrix_payload)

    # 3. Widget: tech_detections_reference
    extracted_detections = []
    for d in detection_records:
        det_id = str(d.get("id") or "").strip()
        score_val = str(d.get("score") or "").strip()
        first_seen = str(d.get("first_seen_at") or "").strip()
        last_seen = str(d.get("last_seen_at") or "").strip()
        dept_onet = str(d.get("department_onet_codes") or "[]").strip()

        if det_id or score_val:
            extracted_detections.append({
                "id": det_id,
                "score": score_val,
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
                "department_onet_codes": dept_onet
            })

    if extracted_detections:
        detections_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "tech_detections_reference",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_detections_count": len(extracted_detections),
                "detections": extracted_detections
            },
            "source_datasets": ["technology_detections"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        detections_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "tech_detections_reference",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["technology_detections"],
            "extracted_at": now,
            "updated_at": now
        }

    widget_store.put(account_id, "tech_detections_reference", detections_payload, db=db)
    results.append(detections_payload)

    # 4. Widget: webstack_breakdown
    web_tech_list = []
    premium_count_str = ""
    spend_est_str = ""
    categories_summary = []

    if webstack_records and len(webstack_records) > 0:
        w_row = webstack_records[0]
        raw_web_tech = str(w_row.get("Technologies Used By Company Website") or "").strip()
        if raw_web_tech:
            web_tech_list = [x.strip() for x in raw_web_tech.split(",") if x.strip()]

        premium_count_str = str(w_row.get("Number Of Premium Technologies") or "").strip()
        spend_est_str = str(w_row.get("Money Spend On Website Technologies") or "").strip()
        raw_cats = str(w_row.get("Technologies Categories") or "").strip()
        if raw_cats:
            categories_summary = [c.strip() for c in raw_cats.split(",") if c.strip()]

    # Explorium 5_Tech_Breakdown, the client's second technographic sheet
    # (DEC-019): the same website stack, grouped by what each technology does.
    # Read from the tech_breakdown dataset, grouped for the Website stack card.
    breakdown = _parse_tech_breakdown(breakdown_records)

    if web_tech_list or premium_count_str or spend_est_str or breakdown:
        webstack_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "webstack_breakdown",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_web_tech_count": len(web_tech_list),
                "premium_tech_count": premium_count_str,
                "web_spend_estimate": spend_est_str,
                "categories_list": categories_summary,
                "technologies": web_tech_list,
                "breakdown": breakdown,
                "breakdown_source": "Explorium 5_Tech_Breakdown" if breakdown else None,
            },
            "source_datasets": ["webstack", "tech_breakdown"] if breakdown else ["webstack"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        webstack_payload = {
            "account_id": account_id,
            "feature_key": "tech_landscape",
            "widget_key": "webstack_breakdown",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["webstack"],
            "extracted_at": now,
            "updated_at": now
        }

    widget_store.put(account_id, "webstack_breakdown", webstack_payload, db=db)
    results.append(webstack_payload)

    # 5. Widget: technographic_hp_recommendations (Inferred).
    #
    # Runs last: it reads the deterministic technographic_map written above,
    # so the HP relationship and category status are already settled before any
    # product is proposed. Cached on a fingerprint that includes the HP
    # knowledge version, so re-extracting a corrected deck fact regenerates it.
    if "recs" not in parts:
        return results

    try:
        from app.services.hp.recommendations import generate_hp_recommendations
        rec_payload = generate_hp_recommendations(account_id)
    except Exception:
        logger.exception("tech landscape: HP recommendation generation failed for %s",
                         account_id)
        rec_payload = None

    if rec_payload:
        widget_store.put(account_id, "technographic_hp_recommendations",
                         {k: v for k, v in rec_payload.items() if k != "_id"}, db=db)
        results.append(rec_payload)

    return results
