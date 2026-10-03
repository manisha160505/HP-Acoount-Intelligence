"""`_fired_by` gives exactly the answer it gave before it was made fast.

It used to test every (rule, cell, term) with `token_present`, lower-casing the
cell and rebuilding the term's pattern each time - 6 million calls and 12
minutes for one real account. It now prepares each evidence list once and
searches each distinct term once. Nothing about the answer may change, so this
pins the new one to the original loop, written out below as it was, over the
inputs that can tell them apart: word boundaries, case, punctuation, regex
characters in a term, excluded look-alikes, empty text and terms, duplicate
terms, the three evidence shapes, and an evidence list that changes between
calls.

Run: python -m pytest tests/test_rulebook_fired_by_equivalence.py -v
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import rulebook as rb
from app.services.hp.product_rules import GLOBAL_EXCLUDE_PHRASES, _is_excluded, token_present


def original_fired_by(row_or_tokens, evidence):
    """The loop as it stood before the change, verbatim in behaviour."""
    tokens = (rb._match_terms(row_or_tokens) if isinstance(row_or_tokens, dict)
              else list(row_or_tokens or []))
    hits, matched = [], set()
    for i, item in enumerate(evidence or []):
        text = rb._evidence_text(item)
        if not text or _is_excluded(text):
            continue
        fired = [t for t in tokens if token_present(t, text)]
        if fired:
            hits.append(i)
            matched.update(fired)
    return hits, matched


WORDS = [*GLOBAL_EXCLUDE_PHRASES[:6], "ai", "AI", "maintenance", "copilot", "Microsoft Intune", "intune", "c++",
         "a.b", "(x)", "zero-trust", "zero trust", "ServiceNow", "servicenow",
         "print", "printer", "printers", "MPS", "mps", "laptop", "laptops",
         "İstanbul", "straße", "STRASSE", "café", "naïve", "東京", "x86_64",
         "hybrid-work", "hybrid work", "", " ", "end-user", "endpoint", "1,000",
         "windows 11", "Windows11", "win11", "fleet"]
GLUE = [" ", ", ", "-", "/", "_", ".", "(", ")", "; ", "", "  "]


def random_text(rng):
    return "".join(rng.choice(WORDS) + rng.choice(GLUE) for _ in range(rng.randint(0, 6)))


def random_item(rng):
    shape = rng.random()
    if shape < 0.45:
        return {"text": random_text(rng), "dataset": "d", "field": "f"}
    if shape < 0.6:
        return {"statement": random_text(rng), "quote": random_text(rng)}
    if shape < 0.7:
        return {"text": None, "quote": random_text(rng)}
    if shape < 0.8:
        return random_text(rng)
    if shape < 0.85:
        return None
    return {"text": random_text(rng)}


def random_terms(rng):
    return [rng.choice(WORDS) for _ in range(rng.randint(0, 8))]


def test_matches_the_original_on_random_inputs():
    rng = random.Random(20261003)
    for _ in range(3000):
        evidence = [random_item(rng) for _ in range(rng.randint(0, 25))]
        terms = random_terms(rng)
        row = {"signal_tokens": terms[: len(terms) // 2],
               "observable_terms": terms[len(terms) // 2:]}
        assert rb._fired_by(terms, evidence) == original_fired_by(terms, evidence)
        assert rb._fired_by(row, evidence) == original_fired_by(row, evidence)


def test_word_boundaries_case_and_regex_characters():
    evidence = [{"text": "Predictive maintenance programme"},
                {"text": "Rolling out an AI PC fleet"},
                {"text": "C++ and a.b and (x) engineers"},
                {"text": "axb"},
                {"text": "MICROSOFT INTUNE, ServiceNow"}]
    for terms in (["ai"], ["c++"], ["a.b"], ["(x)"], ["microsoft intune"], ["servicenow"],
                  ["ai", "ai", "AI"], ["", None], []):
        assert rb._fired_by(terms, evidence) == original_fired_by(terms, evidence)
    hits, matched = rb._fired_by(["ai"], evidence)
    assert hits == [1] and matched == {"ai"}          # never inside "maintenance"
    assert rb._fired_by(["a.b"], evidence)[0] == [2]  # "." is literal, not "any"


def test_excluded_look_alikes_and_empty_cells_are_skipped():
    evidence = ["", None, {"text": ""}, {"text": "vehicle fleet laptops"},
                {"text": "laptops for staff"}]
    assert rb._fired_by(["laptops"], evidence) == original_fired_by(["laptops"], evidence)
    assert rb._fired_by(["laptops"], evidence)[0] == [4]


def test_an_evidence_list_that_changes_is_never_answered_from_before():
    evidence = [{"text": "uses copilot"}, {"text": "uses intune"}]
    assert rb._fired_by(["copilot"], evidence) == ([0], {"copilot"})
    evidence[1]["text"] = "also copilot"          # same list object, new content
    assert rb._fired_by(["copilot"], evidence) == original_fired_by(["copilot"], evidence)
    evidence.append("copilot again")
    assert rb._fired_by(["copilot"], evidence) == ([0, 1, 2], {"copilot"})


def test_returns_the_same_types_as_before():
    hits, matched = rb._fired_by(["ai"], ["ai here", "none", "AI there"])
    assert isinstance(hits, list) and hits == [0, 2]
    assert isinstance(matched, set) and matched == {"ai"}


def test_cache_stays_bounded():
    for n in range(rb._CORPUS_CACHE_SIZE * 3):
        rb._fired_by(["ai"], ["ai %d" % n])
    assert len(rb._CORPUS_CACHE) <= rb._CORPUS_CACHE_SIZE


def test_separator_character_in_text_or_term():
    # Cells are joined with NUL internally; a NUL inside a cell, or a term that
    # contains one, must still give the per-cell answer.
    evidence = ["laptop\x00fleet", "x\x00laptop", "laptop", "\x00", "a\x00b"]
    for terms in (["laptop"], ["fleet"], ["a\x00b"], ["\x00"], ["laptop\x00fleet"], ["b"]):
        assert rb._fired_by(terms, evidence) == original_fired_by(terms, evidence)


def test_repeated_and_overlapping_occurrences():
    # A first occurrence that fails the boundary must not hide a later one.
    evidence = ["aiai ai", "xai ai", "aaa", "printers print", "printprint"]
    for terms in (["ai"], ["aa"], ["print"], ["printers"], ["printprint"]):
        assert rb._fired_by(terms, evidence) == original_fired_by(terms, evidence)
    assert rb._fired_by(["ai"], evidence)[0] == [0, 1]


def test_matches_the_original_on_long_cells():
    rng = random.Random(7)
    for _ in range(300):
        evidence = [" ".join(random_text(rng) for _ in range(rng.randint(5, 40)))
                    for _ in range(rng.randint(1, 60))]
        terms = random_terms(rng)
        assert rb._fired_by(terms, evidence) == original_fired_by(terms, evidence)


def test_no_live_cells_never_inspects_the_terms():
    # The original only called token_present on a live cell, so a term of any
    # type was never looked at when every cell was empty or excluded.
    for evidence in ([], [""], [None], ["vehicle laptops"]):
        assert rb._fired_by([42, "laptops"], evidence) == original_fired_by([42, "laptops"], evidence)
