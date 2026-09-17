# -*- coding: utf-8 -*-
"""Verify Strategy Chat's grounding guarantees, live.

Run from hp-backend:  python scripts/verify_strategy_chat.py [account name]

ABX Feature 8 attaches the strictest guardrails in the document to this feature,
and most of them fail silently if they regress - a wrong answer looks exactly
like a right one. So each is checked by making it happen rather than by reading
the code:

  * the payload is the other features' widget outputs, and touches no raw file
  * it is scoped to one account, and another account's widgets cannot enter it
  * a question the evidence cannot answer is refused in words, not filled in
  * an invented figure is caught by the same gate that passed the real answer
  * history resolves a reference, and the answer is still grounded
  * a multi-hop question draws on several features at once

There is no index behind this feature any more. It reads the whole account -
about 113,000 tokens of widget JSON - in one Gemini call, so the checks that
used to interrogate a retrieval layer now interrogate the payload builder.

Account-agnostic: pass a name, or it defaults to the account with the most
published widgets.
"""
import io
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import logging
logging.disable(logging.INFO)

from app.database.mongodb import connect_to_mongo, get_db
connect_to_mongo()
db = get_db()

from app.services.strategy import chat, context

if len(sys.argv) > 1:
    account = db["accounts"].find_one({"name": sys.argv[1]})
else:
    # Whichever account has the most published widgets - the one with something
    # to answer from. No name is hardcoded.
    counted = sorted(
        ((db["account_widgets"].count_documents(
            {"account_id": str(a["_id"]), "status": "available"}), a)
         for a in db["accounts"].find()),
        key=lambda row: -row[0])
    account = counted[0][1] if counted and counted[0][0] else None
if not account:
    raise SystemExit("no account with published widgets - pass a name")
AID = str(account["_id"])
print("account: %s (%s)" % (account.get("name"), AID))
print()

PASS, FAIL = [], []


def ck(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  [%s] %-54s %s" % ("PASS" if ok else "FAIL", name, str(detail)[:48]))


print("=" * 84)
print("1. THE PAYLOAD IS WIDGET OUTPUTS, NOT RAW FILES")
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
described = context.describe(AID)
payload, sections = context.build(AID)
for mod, name, original in traps:
    setattr(mod, name, original)

ck("building the payload reads no file or dataset", reads["n"] == 0,
   "%d read(s)" % reads["n"])
ck("every contributing feature is represented", len(described["features"]) >= 8,
   "%d features, %d widgets" % (len(described["features"]),
                                described["widgets"]))
ck("the payload is under the guard that catches a runaway widget",
   0 < len(payload) < context.MAX_PAYLOAD_CHARS,
   "%s chars, ~%s-%s tokens" % (format(len(payload), ","),
                                format(described["approx_tokens"][0], ","),
                                format(described["approx_tokens"][1], ",")))
excluded = [s for s in sections
            if s["feature_key"] in context.EXCLUDED_FEATURES]
ck("Content Studio and Message Evaluator stay out", not excluded,
   [s["widget_key"] for s in excluded][:3] or "none")

print()
print("=" * 84)
print("2. ACCOUNT ISOLATION")
print("=" * 84)
others = [a for a in db["accounts"].find() if str(a["_id"]) != AID]
ck("this account has a payload", bool(payload), "%d section(s)" % len(sections))

if others:
    other_id = str(others[0]["_id"])
    other_payload, other_sections = context.build(other_id)

    # Comparing company NAMES is not a valid probe here and was a bug in this
    # script: two accounts can legitimately describe the same company (a
    # re-upload, a staged copy), so a shared name proves nothing either way.
    #
    # What isolation actually means is that every section in this payload came
    # from a row this account owns. That is checked directly.
    owned = {w.get("widget_key") for w in db["account_widgets"].find(
        {"account_id": AID, "status": "available"})}
    strays = [s["widget_key"] for s in sections if s["widget_key"] not in owned]
    ck("every section came from a row this account owns", not strays,
       strays[:3] or "%d section(s) checked" % len(sections))

    # And that nothing unique to the other account crossed over. Its own
    # account id is the one string guaranteed to be unique to it.
    ck("the other account's id appears nowhere in this payload",
       other_id not in payload, other_id)
    ck("the other account builds its own, different payload",
       other_payload != payload,
       "%s vs %s chars" % (format(len(other_payload), ","),
                           format(len(payload), ",")))
else:
    print("  [SKIP] only one account exists - isolation cannot be demonstrated")

ok, reason, _, _ = chat._validate(
    "FACTS:\n1. Something is true [a_section_not_in_this_account].",
    payload, [s["widget_key"] for s in sections])
ck("an answer citing a section not in this payload is rejected", not ok,
   reason[:46])

print()
print("=" * 84)
print("3. VALIDATION BITES")
print("=" * 84)
SAMPLE = ('===== exec_key_metrics (feature: executive_dashboard) =====\n'
          '{"value_text":"IDR 323,392 billion","period":"FY2025"}')
KEYS = ["exec_key_metrics"]

ok, reason, _, _ = chat._validate(
    "FACTS:\n1. Revenue grew by 4271 percent [exec_key_metrics].", SAMPLE, KEYS)
ck("an invented figure is rejected", not ok, reason[:46])

ok, reason, _, _ = chat._validate(
    "FACTS:\n1. Net Revenue for FY2025 was IDR 323,392 billion "
    "[exec_key_metrics].", SAMPLE, KEYS)
ck("a grounded figure passes, despite formatting", ok, reason[:46])

ok, reason, _, _ = chat._validate(
    "FACTS:\n1. Net Revenue for FY2025 was IDR 323,392 billion.", SAMPLE, KEYS)
ck("a fact with no citation at all is rejected", not ok, reason[:46])

ok, reason, _, _ = chat._validate("", SAMPLE, KEYS)
ck("an empty answer is rejected", not ok, reason[:46])


print()
print("=" * 84)
print("4. THE ANSWERS THEMSELVES")
print("=" * 84)


def timed(messages):
    started = time.time()
    result = chat.answer(AID, messages)
    result["_seconds"] = time.time() - started
    return result


result = timed([{"role": "user", "content": "tell me about the revenue"}])
ck("a grounded question is answered", result["available"],
   "%.1fs, %d citation(s)" % (result["_seconds"], len(result["citations"])))

valid = {s["widget_key"] for s in sections}
ck("every citation names a section of this account's payload",
   all(c["evidence_id"] in valid for c in result["citations"]),
   ", ".join(c["evidence_id"] for c in result["citations"])[:46])
ck("every citation carries a label a seller can read",
   all(c.get("source_text") and c.get("dataset") for c in result["citations"]),
   (result["citations"][0].get("dataset") if result["citations"] else "-"))

body = result["answer"]
# {2,} not {5,}: "FACTS:" is six characters, so the old bound could only
# match longer headers like "RECOMMENDATION:" and reported the tightest
# possible answer - one that opened with FACTS: - as unlabelled.
headers = re.findall(r"^[A-Z][A-Z ,'/&-]{2,}:", body, re.M)
ck("the answer uses labelled sections", bool(headers),
   ", ".join(h.strip(":") for h in headers[:3]))
ck("no stray markdown emphasis survives", "**" not in body,
   body[:44].replace("\n", " "))

# A mutation test, because asserting "the published answer has no bad figure"
# passes trivially - the answer was already validated, so the check cannot fail
# and proves nothing. Corrupting it and requiring the SAME gate to reject shows
# the gate is live for this specific answer.
#
# Validated against the WHOLE payload, which is exactly what production checks
# against now. Under retrieval this had to be the retrieved context, and using
# anything narrower made the check fail about one run in five for a reason the
# chat was right about.
keys = [s["widget_key"] for s in sections]
ok_clean, clean_reason, _, _ = chat._validate(body, payload, keys)
ok_dirty, dirty_reason, _, _ = chat._validate(
    body + " Revenue grew 4271 percent year on year [exec_key_metrics].",
    payload, keys)
ck("the gate accepts the published answer", ok_clean, clean_reason[:46])
ck("and rejects the same answer with a figure added", not ok_dirty,
   dirty_reason[:46])

# ABX Step 6 wants an information-not-available ANSWER pointing at the closest
# module - not an error. So `available` stays true: the answer is valid and
# grounded, it just says the platform does not hold this. What must not happen
# is a number being invented to fill the gap.
absent = timed([{"role": "user",
                 "content": "What is the CEO's personal mobile number?"}])
said_no = any(phrase in absent["answer"].lower()
              for phrase in ("does not hold", "not hold", "no information",
                             "not available", "does not have", "not include"))
invented = re.findall(r"\+?\d[\d\s().-]{9,}", absent["answer"])
ck("an unanswerable question is refused in words", said_no,
   absent["answer"][:46].replace("\n", " "))
ck("and no phone-number-like figure is invented", not invented, invented[:2])

foreign = timed([{"role": "user", "content":
                  "How many HP printers did Nestle buy in Brazil last quarter?"}])
ck("a question about another company is not answered about this one",
   any(p in foreign["answer"].lower()
       for p in ("does not hold", "not hold", "no information",
                 "not available", "does not have")),
   foreign["answer"][:46].replace("\n", " "))

print()
print("=" * 84)
print("5. HISTORY RESOLVES, BUT IS NOT EVIDENCE")
print("=" * 84)
first = timed([{"role": "user", "content": "Who is the strongest entry point?"}])
follow = timed([
    {"role": "user", "content": "Who is the strongest entry point?"},
    {"role": "assistant", "content": first["answer"]},
    {"role": "user", "content": "What should I open with when I message them?"}])
ck("the reference is resolved into a standalone question",
   len(follow["question"]) > 40 and "them" not in follow["question"].lower(),
   follow["question"][:46])
ck("the follow-up is answered from the payload", follow["available"],
   "%.1fs, %d citation(s)" % (follow["_seconds"], len(follow["citations"])))
ck("the follow-up's citations resolve too",
   all(c["evidence_id"] in valid for c in follow["citations"]),
   ", ".join(c["evidence_id"] for c in follow["citations"])[:46])

print()
print("=" * 84)
print("6. A MULTI-HOP QUESTION SPANS SEVERAL FEATURES")
print("=" * 84)
# The question retrieval struggled with: it needs a person joined to an intent
# topic joined to a technology, a join that lived only in the graph's
# relationships and depended on one chunk happening to carry all three. Reading
# the whole account, the model makes the join itself.
multi = timed([{"role": "user", "content":
                "Who should I approach about AI workstations, and why?"}])
features = {c.get("dataset") for c in multi["citations"]}
ck("a multi-hop question draws on more than one feature",
   multi["available"] and len(features) >= 2,
   "%.1fs, %s" % (multi["_seconds"], sorted(f for f in features if f)))

print()
print("=" * 84)
timings = [r["_seconds"] for r in (result, absent, foreign, first, follow, multi)]
print("latency: %.1fs median, %.1f-%.1fs over %d questions"
      % (sorted(timings)[len(timings) // 2], min(timings), max(timings),
         len(timings)))
print("%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED: %s" % ", ".join(FAIL))
    sys.exit(1)
