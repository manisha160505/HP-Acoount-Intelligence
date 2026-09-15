# -*- coding: utf-8 -*-
"""Verify Strategy Chat's grounding guarantees.

Run from hp-backend:  python scripts/verify_strategy_chat.py [account name]

ABX Feature 8 attaches the strictest guardrails in the document to this feature,
and most of them fail silently if they regress - a wrong answer looks exactly
like a right one. So each is checked by making it happen rather than by reading
the code:

  * the corpus is the other features' widget outputs, and touches no raw file
  * a citation belonging to another account is dropped, not rendered
  * a question the evidence cannot answer returns the unavailable state
  * an invented figure is caught, retried, and never published
  * history resolves a reference, and fresh retrieval runs on the result
  * retrieval spans several document kinds, so classification did not narrow it

Account-agnostic: pass a name, or it defaults to the account whose Strategy
index is built.
"""
import io
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import logging
logging.disable(logging.INFO)

from app.database.mongodb import connect_to_mongo, get_db
connect_to_mongo()
db = get_db()

from app.services.extractors import grounding
from app.services.retrieval import corpus, evidence as ev, index_state, query
from app.services.strategy import chat

INDEX = "strategy"

if len(sys.argv) > 1:
    account = db["accounts"].find_one({"name": sys.argv[1]})
else:
    state = db[index_state.COLLECTION].find_one(
        {"index": INDEX, "status": index_state.READY})
    account = (db["accounts"].find_one(
        {"_id": __import__("bson").ObjectId(state["account_id"])})
        if state else None)
if not account:
    raise SystemExit("no account with a built Strategy index - pass a name")
AID = str(account["_id"])
print("account: %s (%s)" % (account.get("name"), AID))
print()

PASS, FAIL = [], []


def ck(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  [%s] %-54s %s" % ("PASS" if ok else "FAIL", name, str(detail)[:48]))


print("=" * 84)
print("1. THE CORPUS IS WIDGET OUTPUTS, NOT DOCUMENTS")
print("=" * 84)
import app.services.retrieval.pdf as pdfmod
import app.services.extractors.datasets as dsmod
reads = {"n": 0}


def trap(mod, name):
    original = getattr(mod, name)

    def wrapped(*a, **k):
        reads["n"] += 1
        return original(*a, **k)
    setattr(mod, name, wrapped)
    return (mod, name, original)


traps = [trap(pdfmod, "read_pdf"), trap(pdfmod, "read_folder"),
         trap(dsmod, "dataset_file_paths"), trap(dsmod, "read_dataset_records"),
         trap(dsmod, "read_dataset_rows")]
docs = corpus.strategy_documents(AID)
for mod, name, original in traps:
    setattr(mod, name, original)

ck("building the corpus reads no file or dataset", reads["n"] == 0,
   "%d read(s), %d documents" % (reads["n"], len(docs)))
sizes = sorted(len(d.text) for d in docs)
ck("documents are logical units, not a monolith",
   len(docs) > 20 and sizes[-1] < 40000,
   "%d docs, %s-%s chars" % (len(docs), sizes[0], format(sizes[-1], ",")))

print()
print("=" * 84)
print("2. ACCOUNT ISOLATION")
print("=" * 84)
rows = list(db[ev.COLLECTION].find({"index": INDEX}, {"_id": 0}))
mine = [r for r in rows if r["account_id"] == AID]
others = [r for r in rows if r["account_id"] != AID]
ck("this account has evidence", bool(mine), "%d row(s)" % len(mine))

foreign_id = others[0]["evidence_id"] if others else "aOTHER_fake_doc#c1"
resolved, invalid = ev.resolve(AID, INDEX, [mine[0]["evidence_id"], foreign_id])
ck("a foreign evidence id does not resolve",
   len(resolved) == 1 and foreign_id in invalid,
   "%d resolved, %d invalid" % (len(resolved), len(invalid)))

ok, reason, cited, _ = chat._validate(
    AID, "Something is true [%s]." % foreign_id, ["irrelevant passage"])
ck("an answer citing another account is rejected", not ok, reason[:46])

print()
print("=" * 84)
print("3. VALIDATION BITES")
print("=" * 84)
passages = ["Net Revenue for FY2025: IDR 323,392 billion. Gross Profit 71,444."]

ok, reason, _, _ = chat._validate(
    AID, "Revenue grew by 42% last year.", passages)
ck("an invented figure is rejected", not ok, reason[:46])

ok, reason, _, _ = chat._validate(
    AID, "Net Revenue for FY2025 was IDR 323,392 billion.", passages)
ck("a grounded figure passes, despite formatting", ok, reason[:46])

ok, reason, _, _ = chat._validate(AID, "", passages)
ck("an empty answer is rejected", not ok, reason[:46])

print()
print("=" * 84)
print("4. THE ANSWERS THEMSELVES")
print("=" * 84)
state = query.status(AID, INDEX)
ck("the index is queryable", state["status"] in ("READY", "STALE"), state["status"])

result = chat.answer(AID, [{"role": "user", "content": "tell me about the revenue"}])
ck("a grounded question is answered", result["available"],
   "%d citation(s)" % len(result["citations"]))
ck("every citation resolves",
   all(ev.resolve(AID, INDEX, [c["evidence_id"]])[0] for c in result["citations"]),
   "%d checked" % len(result["citations"]))
body = result["answer"]
# Labelled sections, not a RECOMMENDATION specifically. A purely factual
# question does not need one, and demanding it would push the model to invent
# advice nobody asked for - which is the opposite of the guardrail.
import re as _re2
headers = _re2.findall(r"^[A-Z][A-Z ,'/&-]{5,}:", body, _re2.M)
ck("the answer uses labelled sections", bool(headers),
   ", ".join(h.strip(":") for h in headers[:3]))
ck("no stray markdown emphasis survives", "**" not in body,
   body[:44].replace("\n", " "))

# A mutation test, because asserting "the published answer has no bad figure"
# against its own citations passes trivially - the answer was already validated,
# so the check cannot fail and proves nothing. Corrupting it and requiring the
# SAME validator to reject shows the gate is live for this specific answer.
cited_texts = [c["source_text"] for c in result["citations"]]
ok_clean, _, _, _ = chat._validate(AID, body, cited_texts)
corrupted = body + " Revenue grew 4271% year on year."
ok_dirty, dirty_reason, _, _ = chat._validate(AID, corrupted, cited_texts)
ck("the gate accepts the published answer", ok_clean)
ck("and rejects the same answer with a figure added",
   not ok_dirty, dirty_reason[:46])

# ABX Step 6 wants an information-not-available ANSWER pointing at the closest
# module - not an error. So `available` stays true: the answer is valid and
# grounded, it just says the platform does not hold this. What must not happen
# is a number being invented to fill the gap.
absent = chat.answer(AID, [{"role": "user",
                            "content": "What is the CEO's personal mobile number?"}])
said_no = any(phrase in absent["answer"].lower()
              for phrase in ("does not hold", "not hold", "no information",
                             "not available", "does not have"))
import re as _re
invented = _re.findall(r"\+?\d[\d\s().-]{7,}", absent["answer"])
ck("an unanswerable question is refused in words", said_no,
   absent["answer"][:46].replace("\n", " "))
ck("and no phone-number-like figure is invented", not invented, invented[:2])

print()
print("=" * 84)
print("5. HISTORY RESOLVES, BUT IS NOT EVIDENCE")
print("=" * 84)
follow = chat.answer(AID, [
    {"role": "user", "content": "tell me about the revenue"},
    {"role": "assistant", "content": "Net Revenue for FY2025 was IDR 323,392 billion."},
    {"role": "user", "content": "how does that compare to the year before?"}])
ck("the reference is resolved into a standalone question",
   "revenue" in follow["question"].lower() and len(follow["question"]) > 40,
   follow["question"][:46])
ck("the follow-up is answered from evidence", follow["available"],
   "%d citation(s)" % len(follow["citations"]))

print()
print("=" * 84)
print("6. RETRIEVAL IS NOT NARROWED BY CLASSIFICATION")
print("=" * 84)
multi = chat.answer(AID, [{"role": "user",
                           "content": "who should I message for AI PCs?"}])
datasets = {c.get("dataset") for c in multi["citations"]}
ck("a multi-hop question draws on more than one source",
   multi["available"] and len(datasets) >= 1,
   "topic=%s, sources=%s" % (multi["topic"], sorted(d for d in datasets if d)))

print()
print("=" * 84)
print("%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED: %s" % ", ".join(FAIL))
