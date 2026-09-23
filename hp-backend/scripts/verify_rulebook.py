"""Verify the loaded rulebook against a real account, by making it happen.

    python scripts/verify_rulebook.py                 # every active account
    python scripts/verify_rulebook.py "Astra"         # by name fragment

Nothing here writes. It answers four questions that have to be settled before
any feature switches over to the rulebook:

1. **What actually routes?** Which of the eight opportunity types this account's
   own evidence raises, and which rules that admits. A family nothing reaches is
   a family whose rules can never fire, however well they parsed.

2. **What does C 02 cost?** The rulebook says the engine must not reopen the
   original HP files, so hardware facts stop coming from the 936 deck claims in
   `hp_product_knowledge` and start coming from the matched rule's own list.
   This prints the before and after so the size of that change is a number on a
   page rather than a surprise on a card.

3. **Do the country lists agree?** `services/hp/guardrails.py` holds the runtime
   constants and must keep holding them - two features import them at module
   scope, and a database read there would make an import depend on Mongo. So
   they are compared against the document instead.

4. **Is HP IQ reachable at all?** Version 1.0 is a United States, English-only
   launch, which for a non-US account is not unverifiable but unsatisfiable.

Modelled on `verify_strategy_chat.py`: exercise the real code paths rather than
assert against a fixture.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from app.database.mongodb import get_db
from app.services.hp import rulebook as rb
from app.services.hp.guardrails import (
    COMPETITOR_BLOCK_COUNTRIES,
    SUPERLATIVE_BLOCK_COUNTRIES,
    normalize_country,
)

# Defined in `services/hp/rulebook.py`, so this script verifies against exactly
# the evidence the running features match on. Re-exported under the names this
# script already used.
EVIDENCE_DATASETS = rb.EVIDENCE_DATASETS
_is_meaningful = rb._is_meaningful
account_evidence = rb.account_evidence
account_country = rb.account_country


def has_hp_client_hardware(evidence) -> bool:
    """Whether the estate shows HP client hardware, for the Wolf matrix gate."""
    blob = " ".join(e["text"] for e in evidence).lower()
    return any(t in blob for t in ("hp elitebook", "hp probook", "hp elitedesk",
                                   "hp prodesk", "hp zbook", "hp elite"))


def report_country_lists(book: dict):
    print("\n" + "=" * 78)
    print("COUNTRY LISTS - the document vs the shipped constants")
    for restriction, constant in (("superlative", SUPERLATIVE_BLOCK_COUNTRIES),
                                  ("competitor", COMPETITOR_BLOCK_COUNTRIES)):
        document = rb.blocked_countries(book, restriction)
        code = {str(c).lower() for c in constant}
        row = (book.get("country_lists") or {}).get(restriction) or {}
        aliases = set((row.get("aliases") or {}).keys())

        print("\n  %s: %d in the document, %d in code"
              % (restriction, len(document), len(code)))
        only_code = sorted(code - document - aliases)
        only_doc = sorted(document - code)
        if only_doc:
            print("    IN THE DOCUMENT BUT NOT ENFORCED: %s" % only_doc)
        if only_code:
            print("    enforced but not literally listed: %s" % only_code[:12])
        for note in (row.get("notes") or []):
            print("    the document also says: %s" % note[:150])
        if not only_doc:
            print("    every country the document names is enforced")


def report_account(db, book: dict, account: dict):
    account_id = str(account["_id"])
    name = account.get("name")
    print("\n" + "=" * 78)
    print("ACCOUNT: %s" % name)

    evidence = account_evidence(account_id)
    country = account_country(account_id)
    print("  evidence items: %d | country: %s (normalised: %s)"
          % (len(evidence), country or "unknown",
             normalize_country(country) or "unknown"))

    # 1. routing
    routes = rb.route(book, evidence)
    print("\n  ROUTING - what the account's own evidence raises (C 01)")
    raised = {r["opportunity_type"] for r in routes}
    for row in book["routing"]:
        fired = row["opportunity_type"] in raised
        hits = next((len(r["evidence_indices"]) for r in routes
                     if r["opportunity_type"] == row["opportunity_type"]), 0)
        print("    %-32s %s" % (
            row["opportunity_type"],
            "%4d evidence item(s) -> %s" % (hits, ", ".join(row["families"]))
            if fired else "   - not raised"))

    # 2. rules
    matches = rb.candidates(book, evidence, routes, country)
    chosen = rb.select(matches)
    print("\n  RULES - %d fired" % len(matches))
    for match in matches:
        flag = " [modifier]" if match["modifier_only"] else \
               " [routing]" if match["routing_only"] else ""
        print("    %-10s %-34s %2d evidence%s"
              % (match["rule_label"], (match["offering"] or "")[:34],
                 len(match["evidence_indices"]), flag))
        for condition in match["unverified_conditions"][:2]:
            print("        unverified (C 07): %s" % condition[:100])

    print("\n  SELECTED (C 06 - one main recommendation)")
    if chosen["primary"]:
        print("    primary   : %s - %s" % (chosen["primary"]["rule_label"],
                                           chosen["primary"]["offering"]))
        for match in chosen["secondary"]:
            print("    secondary : %s - %s  (separate evidence)"
                  % (match["rule_label"], match["offering"]))
        for match in chosen["withheld"]:
            print("    withheld  : %s - %s" % (match["rule_label"],
                                               match["withheld_because"]))
    else:
        print("    none: %s" % chosen["reason"])

    # 3. what C 02 costs
    print("\n  FACTS - what C 02 changes")
    deck_claims = 0
    for doc in db["hp_product_knowledge"].find({"_id": {"$ne": "__knowledge_version__"}}):
        deck_claims += len(doc.get("claims") or [])
    rulebook_facts = sum(len(rb.facts_for(m)["allowed_facts"]) for m in matches)
    print("    deck claims in hp_product_knowledge (all decks) : %d" % deck_claims)
    print("    rulebook facts for the rules this account fired : %d" % rulebook_facts)
    if chosen["primary"]:
        facts = rb.facts_for(chosen["primary"])
        print("    the primary recommendation may state %d fact(s):"
              % len(facts["allowed_facts"]))
        for fact in facts["allowed_facts"][:5]:
            print("        %s" % fact[:110])
        for prohibition in facts["prohibitions"][:3]:
            print("        MUST NOT: %s" % prohibition[:100])

    # 4. the two family gates
    print("\n  FAMILY GATES")
    wolf = rb.wolf_offering(book, evidence, has_hp_client_hardware(evidence))
    print("    Wolf Security  : %s" % (wolf["offering"] if wolf
                                       else "no offering this estate can take"))
    iq = rb.iq_availability(book, country)
    print("    HP IQ          : %s" % ("available" if iq["available"]
                                       else iq["reason"]))


def main():
    wanted = " ".join(sys.argv[1:]).strip().lower()
    db = get_db()
    book = rb.load(db)

    if not book["rules"]:
        sys.exit("No rulebook loaded. Run scripts/load_rulebook.py --apply first.")

    print("rulebook: %d rules, %d routing types, version %s"
          % (len(book["rules"]), len(book["routing"]),
             rb.knowledge_version(db)[:16]))

    report_country_lists(book)

    accounts = [a for a in db["accounts"].find({"status": {"$ne": "hidden"}})
                if not wanted or wanted in str(a.get("name") or "").lower()]
    if not accounts:
        sys.exit("No account matched %r" % wanted)

    for account in accounts:
        report_account(db, book, account)

    print("\n" + "=" * 78)
    print("Nothing was written.")


if __name__ == "__main__":
    main()
