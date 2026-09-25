"""Detected technology that an HP offering names as an integration target.

Client direction, 24 Sep:

    "Technology presence alone is not enough to recommend an offering. A
    detected technology can show compatibility or integration fit, but it does
    not show that the customer needs the HP offering.

    Intune + ServiceNow detected -> WXP has a possible fit, but this alone is
    not enough to recommend WXP."

and, on how to word it:

    "'Intune detected; possible WXP integration route' (do not mention no
    evidence)"

So this produces a CONTEXT LINE and nothing else. It never becomes a
recommendation, never contributes to a score, and never reaches the tier model
- a route is a property of HP's product, not evidence about the account. The
account-side question ("is there a need?") is answered by the evidence
pipelines, and where they answer yes the offering is recommended through the
normal path with this line no longer relevant.

The targets are not a hand-typed list. They are read from the rulebook itself:
a rule whose approved facts claim HP connects to something has already named
what it connects to, and HP naming it is what makes it sayable. WXP 07 names
ServiceNow, Microsoft Intune, Power BI, Power Automate and Tableau, which is
the client's own example.
"""

import logging
import re

logger = logging.getLogger(__name__)

# A fact that claims HP connects to something. Same vocabulary as the objection
# playbook's guard, for the same reason - an integration claim can be worded
# many ways and the verb alone is not a reliable anchor.
INTEGRATION_RE = re.compile(
    r"\b(integrat\w*|interoperat\w*|work[s]?\s+with|connect[s]?\s+(to|into)|"
    r"plug[s]?\s+into|native\s+support\s+for|compatible\s+with)\b", re.I)

# Multi-word product names are matched before single words, so "Power BI" is
# found rather than a bare "Power". Anything shorter than this is too generic
# to match safely against a technology export.
MIN_TARGET_LENGTH = 3

# Words that appear capitalised in HP's prose without naming a third-party
# product. HP's own brands are excluded elsewhere, by the offering check.
_NOT_A_TARGET = frozenset((
    "hp", "the", "this", "these", "and", "or", "for", "with", "when", "where",
    "recommend", "use", "using", "supported", "support", "customer", "windows",
    "pc", "pcs", "it", "its", "standard", "series", "platform", "service",
    "services", "solution", "solutions", "enterprise", "professional", "pro",
    "edition", "management", "managed", "secure", "security", "device",
    "devices", "print", "printing", "cloud", "data", "portfolio", "deck",
    # Vendor umbrellas and bare category words. A technology export names
    # "Microsoft" on half its rows, so matching it would put an integration
    # route on almost every account - which is exactly the "technology presence
    # is not enough" trap the client is warning about.
    "microsoft", "google", "amazon", "oracle", "cisco", "ibm", "adobe", "sap",
    "personalization", "access", "control", "direct", "mobile", "connector",
    "modules", "additional", "asset", "tagging", "click", "sure", "wolf",
    "advance", "leadership", "frontline", "specialist", "generalist", "elite",
))

# An offering has to be a product a seller could actually pursue. HP's own
# sales material is listed in the rulebook as an "offering" on some rules, and
# "possible BPS Portfolio Sell-In Deck FY26 integration route" is nonsense.
_NOT_AN_OFFERING_RE = re.compile(
    r"\b(deck|sell-in|playbook|single slide|slides|presentation|portfolio)\b", re.I)


def _candidate_targets(text: str) -> set:
    """Third-party products a fact names, longest phrase first."""
    found = set()
    for phrase in re.findall(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\b", text):
        phrase = phrase.strip()
        if len(phrase) < MIN_TARGET_LENGTH:
            continue
        if phrase.lower() in _NOT_A_TARGET:
            continue
        if phrase.lower().startswith("hp "):
            continue
        found.add(phrase)
    return found


def targets_by_offering(rules) -> dict:
    """{offering: {target, ...}} for every rule that claims an integration."""
    out = {}
    for rule in rules or []:
        facts = " ".join(str(f) for f in (rule.get("allowed_facts") or []))
        if not facts or not INTEGRATION_RE.search(facts):
            continue
        targets = _candidate_targets(facts)
        if not targets:
            continue
        key = (str(rule.get("offering") or "").strip()
               or str(rule.get("rule_label") or "").strip())
        if not key:
            continue
        entry = out.setdefault(key, {"targets": set(),
                                     "rule_label": rule.get("rule_label"),
                                     "family": rule.get("family")})
        entry["targets"].update(targets)
    return out


def routes_for(detected, rules) -> list:
    """Context lines for detected technology HP names as an integration target.

    `detected` is whatever the account's technology export actually names. A
    line is produced only where HP itself named the product, so the sentence a
    seller reads is HP's claim rather than ours.
    """
    def tokens(value):
        return tuple(re.findall(r"[a-z0-9]+", str(value or "").lower()))

    def matches(target_tok, seen_tok):
        """Whole-token match only.

        Substring matching put "Enterprise detected; possible Sure Click
        Enterprise integration route" on the page, and matched Cisco Routers to
        a print module. A target has to appear as complete words: either the
        two names are the same, or HP's name is a run of whole tokens inside
        the detected one, so "Power BI" still finds "Microsoft Power BI" and
        "Tableau" still finds "Tableau Software".
        """
        if not target_tok or not seen_tok:
            return False
        if target_tok == seen_tok:
            return True
        n = len(target_tok)
        return any(seen_tok[i:i + n] == target_tok
                   for i in range(len(seen_tok) - n + 1))

    seen = {str(d or "").strip(): tokens(d)
            for d in (detected or []) if str(d or "").strip()}
    if not seen:
        return []

    lines = []
    for offering, entry in sorted(targets_by_offering(rules).items()):
        if _NOT_AN_OFFERING_RE.search(offering):
            continue
        for target in sorted(entry["targets"]):
            ttok = tokens(target)
            if not ttok or all(t in _NOT_A_TARGET for t in ttok):
                continue
            for shown, stok in seen.items():
                if matches(ttok, stok):
                    lines.append({
                        "technology": shown,
                        "hp_offering": offering,
                        "rule_label": entry["rule_label"],
                        "family": entry["family"],
                        # The client's wording, verbatim. They asked
                        # specifically that it NOT carry a "no evidence" tail.
                        "text": "%s detected; possible %s integration route"
                                % (shown, offering),
                        "is_context_only": True,
                    })
                    break
    # One line per technology, so an account running several of WXP's named
    # targets does not read as several separate findings.
    out, used = [], set()
    for line in lines:
        if line["technology"].lower() in used:
            continue
        used.add(line["technology"].lower())
        out.append(line)
    return out
