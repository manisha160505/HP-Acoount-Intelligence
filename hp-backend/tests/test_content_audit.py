"""The gate audit ledger and the six CSVs.

Spec Section 6 names six audit files and says "an empty audit file is a pass";
Section 7 makes them the release gate. `content_gates.audit_rows()` produced
the rows from the day the gates were built and nothing collected them, so the
files existed as filenames and never as files.
"""

import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import (
    buyer_personas as bp,
    content_audit as ca,
    content_gates as cg,
)


class _Collection:
    def __init__(self):
        self.docs = []

    def insert_many(self, docs):
        self.docs.extend(docs)

    def find(self, query, _projection=None):
        def matches(doc):
            for key, value in query.items():
                if isinstance(value, dict):          # the {"$gte": ...} clause
                    if doc.get(key) < value["$gte"]:
                        return False
                elif doc.get(key) != value:
                    return False
            return True
        return _Sortable([d for d in self.docs if matches(d)])


class _Sortable(list):
    def sort(self, *_args, **_kwargs):
        return self


class _DB:
    def __init__(self):
        self.collection = _Collection()

    def __getitem__(self, _name):
        return self.collection


DIRTY = {
    "opening": "Hi Robert, Poly Studio would suit the rooms.",
    "body_sections": [{"text": "It is industry-leading."}],
    "cta": "Shall I send pricing?",
    "hp_products": ["Poly Studio"],
    "evidence_used": ["A9"],
}


def _findings(asset=None, persona_id="cfo", label_text="x", corpus=None):
    return cg.run(asset if asset is not None else DIRTY,
                  persona_id=persona_id, content_type="email", filled=False,
                  corpus=corpus, supplied_labels=["A1"],
                  label_texts={"A1": label_text},
                  known_names=["Robert Leindl"], competitors=(), industry="",
                  required_keys=())


@pytest.fixture
def db():
    return _DB()


class TestTheLedger:

    def test_a_finding_becomes_a_row(self, db):
        written = ca.record(db, _findings(),
                            account_id="acct-1", persona_id="cfo",
                            content_type="email",
                            outcome=ca.OUTCOME_WITHHELD)
        assert written > 0
        rows = ca.read(db)
        assert all(r["account_id"] == "acct-1" for r in rows)
        assert {r["gate"] for r in rows} >= {"G4", "G7"}

    def test_nothing_to_record_writes_nothing(self, db):
        assert ca.record(db, [], account_id="a", persona_id="cfo",
                         content_type="email",
                         outcome=ca.OUTCOME_PUBLISHED) == 0
        assert ca.read(db) == []

    def test_an_insert_failure_never_reaches_the_caller(self):
        """A seller waiting on an email should not lose it because an audit
        insert failed. The draft is the product; the ledger is paperwork."""
        class _Broken(_DB):
            def __getitem__(self, _name):
                raise RuntimeError("mongo is down")

        assert ca.record(_Broken(), _findings(), account_id="a",
                         persona_id="cfo", content_type="email",
                         outcome=ca.OUTCOME_PUBLISHED) == 0

    def test_rows_are_filterable_by_account_and_surface(self, db):
        ca.record(db, _findings(), account_id="acct-1", persona_id="cfo",
                  content_type="email", outcome=ca.OUTCOME_PUBLISHED)
        ca.record(db, _findings(), account_id="acct-2", persona_id="cfo",
                  content_type="email", outcome=ca.OUTCOME_WITHHELD,
                  surface=ca.SURFACE_REWRITE)
        assert {r["account_id"] for r in ca.read(db, account_id="acct-1")} == {"acct-1"}
        assert {r["surface"] for r in ca.read(db, surface=ca.SURFACE_REWRITE)} \
            == {ca.SURFACE_REWRITE}
        assert {r["outcome"] for r in ca.read(db, outcome=ca.OUTCOME_PUBLISHED)} \
            == {ca.OUTCOME_PUBLISHED}


class TestTheSixFiles:

    def test_every_file_is_written_even_when_empty(self, db, tmp_path):
        """An empty file is the pass signal. A missing file is ambiguous
        between "nothing to report" and "nobody ran the export"."""
        counts = ca.export(db, str(tmp_path))
        assert set(counts) == set(ca.CSV_COLUMNS)
        for name in ca.CSV_COLUMNS:
            assert (tmp_path / name).exists()
            assert counts[name] == 0
        assert ca.is_clean(counts)

    def test_the_six_the_specification_names_are_all_here(self):
        for name in (cg.AUDIT_UNSOURCED_NUMBERS, cg.AUDIT_LINE_ELIGIBILITY,
                     cg.AUDIT_ASK_BOUND, cg.AUDIT_NAME_LEAK,
                     cg.AUDIT_BANNED_PHRASES, cg.AUDIT_EVIDENCE_LABELS):
            assert name in ca.CSV_COLUMNS

    def test_a_finding_lands_in_the_file_section_6_assigns_it(self, db, tmp_path):
        ca.record(db, _findings(), account_id="acct-1", persona_id="cfo",
                  content_type="email", outcome=ca.OUTCOME_WITHHELD)
        counts = ca.export(db, str(tmp_path))
        assert not ca.is_clean(counts)
        assert counts[cg.AUDIT_LINE_ELIGIBILITY] == 1     # Poly to a CFO
        assert counts[cg.AUDIT_NAME_LEAK] == 1            # "Robert" on UNFILLED
        assert counts[cg.AUDIT_BANNED_PHRASES] == 1       # industry-leading
        assert counts[cg.AUDIT_EVIDENCE_LABELS] >= 1      # A9 was never supplied

    def test_the_columns_are_the_ones_section_6_specifies(self, db, tmp_path):
        ca.record(db, _findings(), account_id="acct-1", persona_id="cfo",
                  content_type="email", outcome=ca.OUTCOME_WITHHELD)
        ca.export(db, str(tmp_path))
        with open(tmp_path / cg.AUDIT_LINE_ELIGIBILITY, encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert rows[0][:4] == ["account_id", "persona_id",
                               "denied_line_named", "where_found"]
        assert rows[1][0] == "acct-1"
        assert rows[1][2] == "Poly Studio"

    def test_every_row_says_what_became_of_the_draft(self, db, tmp_path):
        """Recording only published output would leave
        `audit_line_eligibility.csv` empty on a batch where the model tried
        four times to sell Poly to a CFO - and Section 6 calls that file "the
        one to check first"."""
        ca.record(db, _findings(), account_id="a", persona_id="cfo",
                  content_type="email", outcome=ca.OUTCOME_REGENERATED)
        ca.export(db, str(tmp_path))
        with open(tmp_path / cg.AUDIT_LINE_ELIGIBILITY, encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows[0]["outcome"] == ca.OUTCOME_REGENERATED
        assert rows[0]["surface"] == ca.SURFACE_GENERATION
        assert rows[0]["recorded_at"]

    def test_a_clean_account_exports_clean(self, db, tmp_path):
        clean = {"opening": "Your estate is due a refresh.",
                 "body_sections": [{"text": "At HP, Care Pack sets a fixed "
                                            "multi-year cost."}],
                 "cta": "Worth a look at the lifecycle comparison?",
                 "hp_products": ["HP Care Pack Services"],
                 "evidence_used": ["A1"]}
        # A real corpus and a label the opening actually draws on, or G1 and
        # G3 fire on the fixture rather than on the copy.
        from app.services.extractors.grounding import corpus_from_texts
        evidence = "The client estate is due a refresh."
        ca.record(db, _findings(clean, label_text=evidence,
                                corpus=corpus_from_texts([evidence])),
                  account_id="acct-1", persona_id="cfo",
                  content_type="email", outcome=ca.OUTCOME_PUBLISHED)
        counts = ca.export(db, str(tmp_path))
        # The specification's six. `audit_other.csv` is ours and carries the
        # seven gates it assigns no file to - here, G12, because this fixture
        # is a 22-word email against a 120-180 budget. A real draft would not
        # be, and the distinction is worth keeping: a release is gated on the
        # six HP named.
        for name in (cg.AUDIT_UNSOURCED_NUMBERS, cg.AUDIT_LINE_ELIGIBILITY,
                     cg.AUDIT_ASK_BOUND, cg.AUDIT_NAME_LEAK,
                     cg.AUDIT_BANNED_PHRASES, cg.AUDIT_EVIDENCE_LABELS):
            assert counts[name] == 0, name
        assert counts[cg.AUDIT_OTHER] == 1


class TestItIsWiredIn:
    """Both writers. A rewrite is gated by spec 4.8 because it is the version
    the seller actually sends, so its findings belong in the same files."""

    def test_content_studio_records_each_attempt(self):
        import inspect

        from app.services.extractors import content_studio
        source = inspect.getsource(content_studio)
        assert "_record_gate_audit" in source
        assert "audit=attempt_findings" in source
        for outcome in ("OUTCOME_PUBLISHED", "OUTCOME_REGENERATED",
                        "OUTCOME_WITHHELD"):
            assert outcome in source

    def test_the_evaluator_rewrite_records_too(self):
        import inspect

        from app.services.evaluator import evaluate
        source = inspect.getsource(evaluate.rewrite_message)
        assert "content_audit.record" in source
        assert "SURFACE_REWRITE" in source

    def test_the_survivor_is_the_published_one(self):
        """Two attempts, the second publishable: the first is `regenerated`
        and the second is what the seller saw."""
        from app.services.extractors.content_studio import _record_gate_audit
        db = _DB()
        _record_gate_audit(db, [(_findings(), False), (_findings(), True)],
                           account_id="a", persona_id="cfo",
                           content_type="email", asset_id="x", published=True)
        outcomes = {r["outcome"] for r in ca.read(db)}
        assert outcomes == {ca.OUTCOME_REGENERATED, ca.OUTCOME_PUBLISHED}

    def test_when_nothing_passed_every_attempt_is_withheld(self):
        from app.services.extractors.content_studio import _record_gate_audit
        db = _DB()
        _record_gate_audit(db, [(_findings(), False), (_findings(), False)],
                           account_id="a", persona_id="cfo",
                           content_type="email", asset_id="x", published=False)
        assert {r["outcome"] for r in ca.read(db)} == {ca.OUTCOME_WITHHELD}


class TestAChangeToTheLogicReachesWhatIsCached:
    """Both features cache. Neither may serve an answer computed by an older
    version of itself.

    Content Studio's key already carried `prompt_version` and the evidence
    text, so a prompt change or a refreshed widget regenerates. The Evaluator's
    did not: it keyed on the five request inputs only, so a seller who
    resubmitted a draft after the 30 Sep changes was handed a score from a
    scorer that used five dimensions and a different rubric.
    """

    def test_content_studio_keys_on_the_prompt_version_and_the_evidence(self):
        from app.services.extractors import content_studio as cstudio
        persona = {"id": "cfo", "kind": "client_role", "title": "CFO",
                   "subtitle": "", "source": "company_personas"}
        args = (persona, "email", "a topic", "", "", "")
        base = cstudio._request_fingerprint(["A1: the estate is ageing"], *args)
        moved = cstudio._request_fingerprint(
            ["A1: the estate is ageing", "A4: 220 technologies detected"], *args)
        assert base != moved, "new evidence must regenerate"

    def test_the_evaluator_keys_on_the_scorer_s_version(self):
        from app.services.evaluator import evaluate as ev, storage
        request = ("the same draft", "cfo", "conversion", "email", "DEEP")
        old = storage.message_fingerprint(*request, "p2-pack1")
        new = storage.message_fingerprint(
            *request,
            "p%d-pack%d" % (ev.PROMPT_VERSION, bp.PERSONA_PACK_VERSION))
        assert old != new

    def test_the_same_request_under_the_same_version_still_hits_the_cache(self):
        """The point of the key is to avoid paying twice for one answer."""
        from app.services.evaluator import storage
        request = ("the same draft", "cfo", "conversion", "email", "DEEP")
        assert storage.message_fingerprint(*request, "p6-pack3") \
            == storage.message_fingerprint(*request, "p6-pack3")

    def test_both_features_are_rerunnable_per_account(self):
        """What the pipeline owns for these two is the persona context. Each
        is a node in its own feature, so "rebuild this feature for this
        account" works the way it does for the other eleven."""
        from app.services.regen import graph
        by_feature = {}
        for node in graph.NODES:
            by_feature.setdefault(node.feature, []).append(node)
        for feature in ("content_studio", "message_evaluator"):
            nodes = by_feature.get(feature) or []
            assert nodes, feature
            # The persona pack is a logic input on both, so a corrected card
            # marks them stale without anyone remembering to bump.
            assert any("buyer_personas:PERSONA_PACK_VERSION" in ref
                       for node in nodes for ref in node.logic_refs), feature
