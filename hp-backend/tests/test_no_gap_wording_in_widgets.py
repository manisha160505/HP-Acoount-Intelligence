"""Guard: no gap or error wording in published widget data.

Client rule (approved 21 Oct, strict): the client never sees "Unknown",
"N/A", "Not available", "Not disclosed", "No data", "TBD", "failed", fault
lists and the like. An absent value is published empty (the UI hides empty
fields); the reason lives only in internal fields - data_gaps,
unavailable_reason, detection_note, generation metadata - which the dashboard
does not render.

Each feature below is run end to end on deliberately sparse inputs with every
model call failing (the fault-injection tests' approach: nothing touches the
network or a real database), and every string in the published `data` is
checked, except under the internal keys listed in INTERNAL_KEYS. Each of those
is there because hp-frontend/src/app/dashboard/page.tsx does not render it;
the reason is given beside it.

Features: Stakeholder Map, Executive Dashboard (summary, metrics, urgency),
Tech Landscape, Opportunity Map, Objection Playbook, Recent News, Content
Studio (fallback asset and the neutral failure line), and Intent / Hiring with
nothing on file.

Run: .venv/bin/python -m pytest tests/test_no_gap_wording_in_widgets.py -v
"""

import inspect
import os
import re
import sys
from types import SimpleNamespace

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from app.core import llm
from regen_fakes import FakeDb

BANNED = (
    "Unknown", "Unknown Contact", "N/A", "Not available", "Not provided",
    "Not disclosed", "Unavailable", "No data", "TBD", "Missing", "Pending",
    "No signal", "no evidence", "not found", "not recorded", "failed",
    "could not", "requires an LLM API key",
)
# Word boundaries, so an enum code such as "no_data" or "missing_input" (a key
# or a code the UI maps, never prints) is not a hit, but "N/A", "Failed" and
# "could not" in prose are.
BANNED_RE = re.compile(
    r"(?<![\w/])(?:%s)(?![\w/])" % "|".join(re.escape(p) for p in BANNED), re.I)

# Keys whose values the dashboard never renders. Each is internal by design.
INTERNAL_KEYS = {
    # The gap / failure reasons themselves (regen/data_gaps.py reads them).
    "data_gaps", "unavailable_reason", "unavailable_cause", "detection_note",
    "fallback_note", "entity_note", "generation", "generation_note",
    "zero_reason", "evidence_basis_note",
    # `data.notice`: page.tsx no longer reads it (the empty-state notices and
    # their SHOW_EMPTY_STATE_NOTICES flag were removed, 21 Oct). Content
    # Studio's `last_error.notice` is checked separately below for the
    # approved neutral line.
    "notice",
    # Urgency: the dashboard renders each driver's label and value only; the
    # term bases, notes and the missing-input bookkeeping are calculation
    # provenance (the reason a component scored 0 sits on its term).
    "terms", "missing_inputs", "missing_input_rule", "scope_note",
    "formula_authority", "caveats", "notes",
    # Intent-style availability codes and the topic widget's `message`: no
    # longer read by page.tsx, like `notice`.
    "availability", "message",
    # Model-call accounting and audit rows.
    "audit_log", "attempts", "pipeline", "grounding_report",
}
# Enum codes the UI maps to a label (or to nothing) and never prints raw.
ENUM_CODES = {
    # Recent News: 'unknown' renders no badge (eventStatusBadge default -> null).
    ("event_status", "unknown"),
}


def gap_wording(value, path="data"):
    """(path, text) for every client-visible string carrying banned wording."""
    hits = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in INTERNAL_KEYS:
                continue
            if isinstance(v, str) and (k, v.strip().lower()) in ENUM_CODES:
                continue
            hits += gap_wording(v, "%s.%s" % (path, k))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            hits += gap_wording(v, "%s[%d]" % (path, i))
    elif isinstance(value, str) and BANNED_RE.search(value):
        hits.append((path, value))
    return hits


def assert_clean(widgets):
    widgets = widgets if isinstance(widgets, list) else [widgets]
    hits = []
    for w in widgets:
        if not isinstance(w, dict):
            continue
        data = w.get("data") if "widget_key" in w else w
        hits += [("%s:%s" % (w.get("widget_key", "?"), p), t) for p, t in gap_wording(data)]
    assert not hits, "gap wording in published widget data:\n" + "\n".join(
        "  %s = %r" % (p, t[:160]) for p, t in hits)


def test_the_walker_catches_what_it_should():
    assert gap_wording({"a": "Unknown"}) and gap_wording({"a": ["N/A"]})
    assert gap_wording({"a": {"b": "The call failed."}})
    assert gap_wording({"a": "Not disclosed"}) and gap_wording({"a": "TBD"})
    assert not gap_wording({"unavailable_reason": "the call failed"})
    assert not gap_wording({"a": "no_data", "b": "missing_input", "c": "Confirmed"})
    assert not gap_wording({"event_status": "unknown"})
    assert not gap_wording({"a": "known issue", "b": "unpending"})


# ---------------------------------------------------------------- harness

ACCOUNT = str(ObjectId())
_PATCHED_NAMES = ("read_dataset_records", "_read_dataset_records", "_read_dataset_csv")


@pytest.fixture
def world(monkeypatch):
    """A FakeDb, dataset rows served from `rows`, and every model call failing.

    Every `app.*` module that imported `get_db` or a dataset reader by name is
    patched, so no feature reaches a real database or file."""
    db = FakeDb()
    db["accounts"].insert_one({"_id": ObjectId(ACCOUNT), "name": "Acme Corp",
                               "domain": "acme.example"})
    rows: dict = {}

    def records(_aid, key, *_a, **_k):
        return [dict(r) for r in rows.get(key, [])]

    # Import the features first, so their modules are in sys.modules.
    from app.services.dashboard import urgency  # noqa: F401
    from app.services.extractors import (  # noqa: F401
        content_studio,
        executive_dashboard,
        objection_playbook,
        recent_news_signals,
        solution_narrative_opportunity_map,
        stakeholder_map,
        tech_landscape,
    )

    for name, module in list(sys.modules.items()):
        if not name.startswith("app.") or module is None:
            continue
        if getattr(module, "get_db", None) is not None and name != "app.database.mongodb":
            monkeypatch.setattr(module, "get_db", lambda: db, raising=False)
        for attr in _PATCHED_NAMES:
            if callable(getattr(module, attr, None)):
                monkeypatch.setattr(module, attr, records)
        if callable(getattr(module, "read_dataset_rows", None)):
            monkeypatch.setattr(module, "read_dataset_rows", lambda *_a, **_k: [])
        if callable(getattr(module, "dataset_file_paths", None)):
            monkeypatch.setattr(module, "dataset_file_paths", lambda *_a, **_k: [])
        if callable(getattr(module, "generate_gpt4o_json_completion", None)):
            monkeypatch.setattr(module, "generate_gpt4o_json_completion",
                                lambda *_a, **_k: None)
    from app.database import mongodb
    monkeypatch.setattr(mongodb, "get_db", lambda: db)
    monkeypatch.setattr(llm, "get_openai_client", lambda *_a, **_k: None)
    return SimpleNamespace(db=db, rows=rows)


def run(fn, *args, **kwargs):
    """The feature itself, without the local-file check in front of it."""
    return inspect.unwrap(fn)(*args, **kwargs)


SPARSE_FIRMO = [{"Company Name": "Acme Corp", "Business Description": "",
                 "Number Of Employees Range": "", "Yearly Revenue Range": ""}]

SPARSE_CONTACTS = [
    # A name and nothing else.
    {"Prospect full_name": "Eve Blank", "Prospect prospect_id": "eve"},
    # A title and nothing else - no name.
    {"Prospect job_title": "IT Director", "Contact professions_email": "itd@acme.example"},
    # Neither: nothing to show.
    {"Contact professions_email": "nobody@acme.example"},
    # A complete row.
    {"Prospect full_name": "Zoe Abbott", "Prospect job_title": "Chief Information Officer",
     "Prospect job_department_main": "IT", "Prospect job_level_main": "cxo",
     "Prospect prospect_id": "zoe"},
]


# ---------------------------------------------------------------- features

class TestStakeholderMap:

    def test_sparse_contacts_and_a_dead_model(self, world, monkeypatch):
        from app.services.extractors import stakeholder_map as sm
        world.rows.update(prospect_contacts=SPARSE_CONTACTS, firmographics=SPARSE_FIRMO)
        monkeypatch.setattr(sm.translate, "to_english", lambda *_a, **_k: {})
        monkeypatch.setattr(sm.personas, "read_roles", lambda _aid: [])
        out = run(sm.extract_stakeholder_map, ACCOUNT)
        assert_clean(out)
        grid = {w["widget_key"]: w for w in out}["stakeholder_contacts_grid"]["data"]
        names = sorted((c["full_name"], c["name_is_title"]) for c in grid["contacts"])
        # No name: the title labels the card. Neither: the contact is left off.
        assert names == [("Eve Blank", False), ("IT Director", True), ("Zoe Abbott", False)]

    def test_no_contacts(self, world, monkeypatch):
        from app.services.extractors import stakeholder_map as sm
        monkeypatch.setattr(sm.translate, "to_english", lambda *_a, **_k: {})
        monkeypatch.setattr(sm.personas, "read_roles", lambda _aid: [])
        assert_clean(run(sm.extract_stakeholder_map, ACCOUNT))


class TestExecutiveDashboard:

    def test_sparse_firmographics(self, world):
        from app.services.extractors import executive_dashboard as ed
        world.rows.update(firmographics=SPARSE_FIRMO)
        out = run(ed.extract_executive_dashboard, ACCOUNT)
        assert_clean(out)
        urgency = next(w for w in out if "drivers" in w)
        for driver in urgency["drivers"]:
            assert not any(BANNED_RE.search(line) for line in driver["rationale_lines"])

    def test_nothing_on_file(self, world):
        from app.services.extractors import executive_dashboard as ed
        assert_clean(run(ed.extract_executive_dashboard, ACCOUNT))


class TestTechLandscape:

    def test_a_thin_stack(self, world):
        from app.services.extractors import tech_landscape as tl
        world.rows.update(firmographics=SPARSE_FIRMO, technographics=[
            {"Full Tech Stack": "Microsoft Windows 11, Zoom"}])
        out = run(tl.extract_tech_landscape, ACCOUNT)
        assert_clean(out)

    def test_no_technographics(self, world):
        from app.services.extractors import tech_landscape as tl
        assert_clean(run(tl.extract_tech_landscape, ACCOUNT))

    def test_whitespace_detection_status_is_blank(self):
        from app.services.extractors.tech_landscape import _normalise_hp_fields
        cats = [{"category_key": "pc_laptop_brands", "status_badge": "Displacement opportunity",
                 "vendors": [{"vendor_name": "HP Inc.", "is_whitespace": True}]}]
        _normalise_hp_fields(cats, {})
        vendor = cats[0]["vendors"][0]
        assert vendor["detection_status"] == ""
        assert vendor["detection_note"], "the reason is kept internally"


class TestOpportunityMap:

    def test_sparse_inputs_and_a_dead_model(self, world, monkeypatch):
        from app.services.extractors import solution_narrative_opportunity_map as opp
        world.rows.update(firmographics=SPARSE_FIRMO,
                          technographics=[{"Full Tech Stack": "Zoom"}])
        monkeypatch.setattr(opp.widget_store, "get", lambda *_a, **_k: None)
        assert_clean(run(opp.extract_solution_narrative_opportunity_map, ACCOUNT))

    def test_nothing_on_file(self, world, monkeypatch):
        from app.services.extractors import solution_narrative_opportunity_map as opp
        monkeypatch.setattr(opp.widget_store, "get", lambda *_a, **_k: None)
        assert_clean(run(opp.extract_solution_narrative_opportunity_map, ACCOUNT))


class TestObjectionPlaybook:

    def _patch(self, monkeypatch):
        from app.services.extractors import objection_playbook as op
        monkeypatch.setattr(op.cs, "knowledge_version", lambda _db: "cs-v")
        monkeypatch.setattr(op.rb, "knowledge_version", lambda _db: "rb-v")
        monkeypatch.setattr(op.rb, "account_evidence", lambda _aid: [])
        monkeypatch.setattr(op.rb, "account_country", lambda _aid: "")
        monkeypatch.setattr(op, "_rulebook_claims", lambda *_a, **_k: {})
        monkeypatch.setattr(op.cs, "cited_above", lambda *_a, **_k: set())
        monkeypatch.setattr(op.cs, "allocate", lambda *_a, **_k: None)
        return op

    def test_thin_technographics_and_a_dead_model(self, world, monkeypatch):
        op = self._patch(monkeypatch)
        world.rows.update(firmographics=SPARSE_FIRMO, prospect_contacts=SPARSE_CONTACTS,
                          technographics=[{"Collaboration": "Zoom", "Full Tech Stack": "Zoom"}])
        assert_clean(run(op.extract_objection_playbook, ACCOUNT))

    def test_no_technology_evidence(self, world, monkeypatch):
        op = self._patch(monkeypatch)
        assert_clean(run(op.extract_objection_playbook, ACCOUNT))


class TestRecentNews:

    def test_sparse_news_and_a_dead_model(self, world):
        from datetime import UTC, datetime, timedelta

        from app.services.extractors import recent_news_signals as rns
        day = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%d")
        world.rows.update(google_news=[
            {"event_headline": "Acme opens a new plant", "event_date": day,
             "event_url": "https://www.reuters.com/acme-plant"},
            {"event_headline": "Acme names a new CIO", "event_date": day}])
        assert_clean(run(rns.extract_recent_news_signals, ACCOUNT))

    def test_no_news(self, world):
        from app.services.extractors import recent_news_signals as rns
        assert_clean(run(rns.extract_recent_news_signals, ACCOUNT))


class TestContentStudio:
    """The parts of Content Studio the client reads: persona subtitles, the
    fallback asset's printed style line, and `last_error.notice` - which the
    page DOES render, so it must be the approved neutral line, with no faults
    beside it (the page lists `last_error.faults` when present)."""

    def _ctx(self, with_account_fact=True):
        from app.services.extractors import content_studio as cstudio
        from app.services.extractors.grounding import GroundingReport, build_corpus
        persona = {"id": "contact_zoe", "kind": "named", "source": "Source A",
                   "title": "Chief Information Officer", "full_name": "",
                   "subtitle": "Information Technology \u00b7 C-Suite", "contact_id": "zoe",
                   "department": "Information Technology", "seniority": "C-Suite"}
        labels = {"P1": "Title: Chief Information Officer"}
        if with_account_fact:
            labels["A1"] = "Distributes industrial parts across Europe."
        ground = build_corpus({"evidence_block": [{"text": t} for t in labels.values()]})
        return {"contract": cstudio.CONTENT_TYPE_CONTRACTS["email"], "persona": persona,
                "company_name": "Acme Corp",
                "account_block": "\n".join("[%s] %s" % kv for kv in labels.items()
                                           if kv[0][0] == "A"),
                "persona_block": "[P1] Title: Chief Information Officer",
                "labels": labels, "ground": ground,
                "report": GroundingReport(ground, ["subject_line", "opening",
                                                   "body_sections", "cta"]),
                "banned_names": [], "fingerprint": "f" * 40, "instructions_text": "",
                "guardrails_text": "", "topic": "Device refresh", "additional_context": "",
                "content_type": "email", "industry": ""}

    def _studio(self, world, monkeypatch, ctx):
        from app.services.extractors import content_studio as cstudio
        monkeypatch.setattr(cstudio, "_build_generation_context", lambda *_a, **_k: ctx)
        monkeypatch.setattr(cstudio, "_record_gate_audit", lambda *_a, **_k: None)
        monkeypatch.setattr(cstudio.cs, "allocate", lambda *_a, **_k: None)
        monkeypatch.setattr(cstudio.cs, "cited_above", lambda *_a, **_k: set())
        return cstudio

    def test_a_dead_model_publishes_the_template_with_no_failure_note(self, world, monkeypatch):
        cstudio = self._studio(world, monkeypatch, self._ctx())
        out = cstudio.generate_content_asset(ACCOUNT, "contact_zoe", "email", "Device refresh")
        assert out["data"]["latest"]["is_fallback"] is True
        assert_clean(out)

    def test_nothing_publishable_reads_neutrally_and_lists_no_faults(self, world, monkeypatch):
        cstudio = self._studio(world, monkeypatch, self._ctx(with_account_fact=False))
        out = cstudio.generate_content_asset(ACCOUNT, "contact_zoe", "email", "Device refresh")
        last_error = out["data"]["last_error"]
        assert last_error["notice"] == "Something went wrong. Please try again."
        assert "faults" not in last_error
        assert last_error["generation"]["faults"], "the faults are kept internally"
        assert_clean(out)

    def test_a_nameless_contact_has_no_placeholder_name(self, world):
        from app.services.extractors import content_studio as cstudio
        world.db["account_widgets"].insert_one({
            "account_id": ACCOUNT, "widget_key": "stakeholder_contacts_grid",
            "status": "available", "data": {"contacts": [{
                "contact_id": "zoe", "full_name": "Chief Information Officer",
                "name_is_title": True, "title": "Chief Information Officer",
                "source": "Source A", "hp_relevance_band": "high",
                "is_priority_contact": True, "stakeholder_score": 80,
                "normalized_department": "Information Technology",
                "seniority_band": "C-Suite", "influence_type": "Decision Maker"}]}})
        personas = cstudio._derive_named_personas(world.db, ACCOUNT)
        assert personas and personas[0]["full_name"] is None
        assert personas[0]["subtitle"] == "Information Technology \u00b7 C-Suite"
        assert_clean({"personas": personas})
        assert not any(k == "Name" for k, _v in cstudio._persona_evidence(personas[0]))


class TestIntentAndHiring:
    """No data on file: the panels publish empty, the reason stays internal."""

    def test_intent_with_nothing_on_file(self, world):
        from app.services.extractors import intent_demand_signals as ids
        assert_clean(run(ids.extract_intent_demand_signals, ACCOUNT))

    def test_hiring_with_nothing_on_file(self, world):
        from app.services.extractors import hiring_signals
        assert_clean(run(hiring_signals.extract_hiring_signals, ACCOUNT))
