"""Where the Objection Playbook's technology evidence comes from.

4_Technographics first. When it holds no data for an account, the website
technology in tech_breakdown (client's round-2 load guidance: "website tech
when no technographics"). With neither, no card is written and nothing is
inferred from any other dataset - not job-ad tags, not PredictLeads technology
detections (whose technology names are missing at source).

Run: python -m pytest tests/test_objection_tech_fallback.py -v
"""

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import hiring_signals, objection_playbook as op

TECHNOGRAPHICS_ROW = {
    "Collaboration": "Zoom, Slack",
    "It Security": "CrowdStrike",
    "Full Tech Stack": "Zoom, Slack, CrowdStrike, Salesforce",
}

# Shaped like ALPS ALPINE's tech_breakdown.csv: vendor groups, page metadata
# columns, and no HP-area vendor at all.
ALPS_LIKE_BREAKDOWN = {
    "Copyright": "Other: Copyright Year 2019",
    "Language": "Other: German, Japanese HREF LANG",
    "Mx": "Other: Salesforce SPF, DMARC, Microsoft Exchange Online, Office 365 Mail",
    "Cms": "Other: Atlassian Cloud | Job Board: rexx systems",
    "Web Server": "Other: nginx",
}

BREAKDOWN_WITH_A_VENDOR = {
    "Widgets": "Video: Zoom | Other: Font Awesome",
    "Web Server": "Other: nginx",
}

EMPTY_TECHNOGRAPHICS = [dict.fromkeys([*op.TECHNOGRAPHICS_CATEGORY_COLUMNS, "Technology", "Full Tech Stack"], "")]

FIRMOGRAPHICS = [{"Business Description": "Makes electronic components.",
                  "Linkedin Industry Category": "Electronics"}]


def _datasets(technographics=None, tech_breakdown=None, extra=None):
    data = {
        "technographics": technographics or [],
        "tech_breakdown": [tech_breakdown] if tech_breakdown else [],
        "firmographics": FIRMOGRAPHICS,
        "prospect_contacts": [],
    }
    data.update(extra or {})
    return data


class _Store:
    def __init__(self):
        self.put_calls = {}

    def put(self, account_id, widget_key, payload, db=None):
        self.put_calls[widget_key] = payload

    def get(self, account_id, widget_key, db=None):
        return None


class _DB:
    def __getitem__(self, name):
        raise AssertionError("no collection should be read: %s" % name)


@pytest.fixture
def run(monkeypatch):
    """Run the playbook on in-memory datasets. The card generator is replaced:
    it records what it was given and returns one card per area, so these tests
    pin the evidence, never a model's prose."""

    def _run(datasets):
        reads = []

        def read(account_id, key, strict=True):
            reads.append(key)
            return datasets.get(key, [])

        generated = {}

        def fake_generate(account_id, areas, company_name, description,
                          industry="", evidence_source="technographics"):
            generated["areas"] = areas
            generated["source"] = evidence_source
            return {"status": "available",
                    "data": {"cards": [{"area": a["area"], "evidence": a["evidence"],
                                        "evidence_source": evidence_source}
                                       for a in areas]}}

        store = _Store()
        monkeypatch.setattr(op, "read_dataset_records", read)
        monkeypatch.setattr(op, "get_db", _DB)
        monkeypatch.setattr(op, "widget_store", store)
        monkeypatch.setattr(op, "generate_objection_cards", fake_generate)
        import app.services.extractors.tech_landscape  # noqa: F401 - imported lazily by op

        extract = inspect.unwrap(op.extract_objection_playbook)
        extract("not-an-object-id")
        return store.put_calls, generated, reads

    return _run


class TestSourcePriority:
    def test_technographics_available_uses_technographics(self, run):
        widgets, generated, reads = run(_datasets(
            technographics=[TECHNOGRAPHICS_ROW], tech_breakdown=ALPS_LIKE_BREAKDOWN))
        ctx = widgets["objection_incumbent_context"]["data"]
        cards = widgets["objection_reframe_cards"]["data"]
        assert generated["source"] == "technographics"
        assert ctx["technology_evidence_source"] == "technographics"
        assert cards["technology_evidence_source"] == "technographics"
        assert ctx["incumbent_technologies"] == ["Zoom", "Slack", "CrowdStrike", "Salesforce"]
        assert all(a["evidence"].startswith("technographics -> ") for a in generated["areas"])
        # The fallback is not consulted when technographics has data.
        assert "tech_breakdown" not in reads

    def test_no_technographics_with_tech_breakdown_uses_tech_breakdown(self, run):
        widgets, generated, _ = run(_datasets(
            technographics=EMPTY_TECHNOGRAPHICS, tech_breakdown=ALPS_LIKE_BREAKDOWN))
        ctx = widgets["objection_incumbent_context"]["data"]
        cards = widgets["objection_reframe_cards"]
        assert generated["source"] == "tech_breakdown"
        assert ctx["technology_evidence_source"] == "tech_breakdown"
        assert cards["data"]["technology_evidence_source"] == "tech_breakdown"
        assert cards["status"] == "available"
        assert len(generated["areas"]) == len(op.AREA_CATEGORY_COLUMNS)
        for area in generated["areas"]:
            assert area["evidence"].startswith("tech_breakdown -> ")
            assert "technographics" not in area["evidence"]
        # Website tech is not an incumbent estate.
        assert ctx["incumbent_technologies"] == []
        assert widgets["objection_incumbent_context"]["source_datasets"][0] == "tech_breakdown"

    def test_header_only_technographics_file_falls_back(self, run):
        """The split writes a header-only file when the sheet is empty, which
        reads as no records at all."""
        _, generated, _ = run(_datasets(technographics=[],
                                        tech_breakdown=ALPS_LIKE_BREAKDOWN))
        assert generated["source"] == "tech_breakdown"

    def test_neither_source_means_no_technology_evidence(self, run):
        widgets, generated, _ = run(_datasets(technographics=EMPTY_TECHNOGRAPHICS))
        cards = widgets["objection_reframe_cards"]
        ctx = widgets["objection_incumbent_context"]["data"]
        assert generated == {}, "no card may be generated without technology evidence"
        assert cards["status"] == "empty"
        assert cards["data"]["cards"] == []
        assert cards["data"]["technology_evidence_source"] == "none"
        assert "No technology evidence available" in cards["data"]["notice"]
        assert ctx["technology_evidence_source"] == "none"
        assert ctx["area_evidence"] == []

    def test_a_tech_breakdown_of_page_metadata_only_is_no_evidence(self, run):
        widgets, generated, _ = run(_datasets(
            tech_breakdown={"Copyright": "Other: Copyright Year 2019",
                            "Language": "Other: English HREF LANG"}))
        assert generated == {}
        assert widgets["objection_reframe_cards"]["data"]["technology_evidence_source"] == "none"


class TestNoVendorIsInvented:
    def test_absent_vendor_is_reported_absent(self):
        source, row = "tech_breakdown", {op.WEBSITE_STACK_COLUMN:
                                          "Salesforce SPF, DMARC, Office 365 Mail, nginx"}
        for area in op._build_area_evidence(row, source):
            assert area["detected_vendors"] == []
            assert area["not_in_technographics"] is True
            assert area["evidence"] == (
                "tech_breakdown -> " + area["area"] + ": no vendor for this area "
                "appears in this account's website technology evidence")

    def test_generic_website_tech_is_not_read_as_a_vendor(self):
        """"Office 365 Mail" is a mail record on the website, not the vendor
        token "microsoft office 365"; nothing is inferred from it."""
        row = {op.WEBSITE_STACK_COLUMN: "Office 365 Mail, Microsoft Exchange Online"}
        collab = next(a for a in op._build_area_evidence(row, "tech_breakdown")
                      if a["area"] == "Collaboration")
        assert collab["detected_vendors"] == []

    def test_a_vendor_actually_present_is_shown_with_its_source(self, run):
        _, generated, _ = run(_datasets(tech_breakdown=BREAKDOWN_WITH_A_VENDOR))
        collab = next(a for a in generated["areas"] if a["area"] == "Collaboration")
        assert collab["detected_vendors"] == ["Zoom"]
        assert collab["evidence"] == "tech_breakdown -> Collaboration | Website stack: Zoom"
        others = [a for a in generated["areas"] if a["area"] != "Collaboration"]
        assert all(a["detected_vendors"] == [] for a in others)

    def test_technographics_evidence_wording_is_unchanged(self):
        """Existing cards are cached on these exact strings; a change in them
        would re-run the model for every account that has technographics."""
        areas = {a["area"]: a for a in op._build_area_evidence(TECHNOGRAPHICS_ROW)}
        assert areas["Collaboration"]["evidence"] == (
            "technographics -> Collaboration | Collaboration: Zoom, Slack")
        assert areas["Print / MPS"]["evidence"] == (
            "technographics -> Print / MPS: no vendor for this area appears in this "
            "account's technographics evidence")


class TestOtherSourcesAreNotEvidence:
    def test_job_tags_and_predictleads_detections_are_never_read(self, run):
        _, generated, reads = run(_datasets(
            technographics=EMPTY_TECHNOGRAPHICS,
            extra={"job_openings": [{"tags": '["Zoom", "Intune"]'}],
                   "technology_detections": [{"technology_name": "Dell"}]}))
        assert "job_openings" not in reads
        assert "technology_detections" not in reads
        assert generated == {}

    def test_empty_hiring_tags_stay_empty(self):
        jobs = [{"tags": "[]"}, {"tags": ""}, {"tags": None}]
        assert hiring_signals.tech_tags(jobs, set())["tags"] == []
        payload = hiring_signals._payload("a", "hiring_tech_tags", {}, None, {})
        assert payload["status"] == "empty"
        assert payload["data"] == {}


class TestTheFallbackIsNotNamedToTheBuyer:
    def test_naming_the_website_evidence_is_a_fault(self):
        """Seen on the first ALPS-style run: "we don't see specific collaboration
        vendors in your public website technology" - our research gap, said to
        the buyer."""
        for reframe in ("While we don't see a vendor in your public website technology, "
                        "HP offers Poly.",
                        "No vendor is detected in your website technology; HP offers Poly."):
            faults = op._claim_faults(reframe, [], "japan")
            assert faults and "internal vocabulary" in faults[0], reframe


# =============================================================================
# The pipeline senses new data: an upload of either source marks the section
# stale, and the next explicit run picks the right source. Driven through the
# real regeneration engine with the real objection node (its declared datasets
# are exactly what production uses), on the in-memory Mongo fake.
# =============================================================================

TECHNO_HEADER = ",".join([*op.TECHNOGRAPHICS_CATEGORY_COLUMNS, "Full Tech Stack"]) + "\n"
FIRMO_CSV = "Business Description,Linkedin Industry Category\nMakes parts.,Electronics\n"
BREAKDOWN_CSV = 'Mx,Web Server\n"Other: Office 365 Mail, DMARC",Other: nginx\n'
BREAKDOWN_CSV_V2 = 'Widgets,Web Server\n"Video: Zoom",Other: nginx\n'
TECHNO_CSV = (",".join(["Collaboration", "Full Tech Stack"]) + "\n"
              + '"Zoom, Slack","Zoom, Slack"\n')


@pytest.fixture
def pipe(tmp_path, monkeypatch):
    from app.database import mongodb
    from app.services.regen import jobs
    from app.services.regen.graph import DEFAULT
    from regen_fakes import FakeDb
    from test_regen_engine import Harness

    monkeypatch.setattr(jobs, "GATE_RETRY_SECONDS", 0)
    db = FakeDb()
    monkeypatch.setattr(mongodb.db_instance, "db", db)

    def fake_generate(account_id, areas, company_name, description,
                      industry="", evidence_source="technographics"):
        return {"account_id": account_id, "feature_key": "objection_playbook",
                "widget_key": "objection_reframe_cards", "status": "available",
                "data": {"cards": [{"area": a["area"], "evidence": a["evidence"],
                                    "detected_vendors": a["detected_vendors"],
                                    "evidence_source": evidence_source}
                                   for a in areas]}}

    monkeypatch.setattr(op, "generate_objection_cards", fake_generate)

    node = DEFAULT.nodes["objection"]
    h = Harness(db, tmp_path, nodes=(node,))
    h.runners["objection"] = lambda account_id, **_kw: op.extract_objection_playbook(account_id)
    h.engine = h.make_engine()
    h.engine.ensure_indexes()
    return h


def _source(h, account_id):
    cards = h.widget(account_id, "objection_reframe_cards")
    return cards["data"]["technology_evidence_source"], cards


class TestThePipelineSensesNewData:
    def test_both_sources_are_declared_triggers(self):
        from app.api.v1.account_data import _features_for_dataset
        from app.services.regen.graph import DEFAULT

        for key in ("technographics", "tech_breakdown"):
            assert "objection" in DEFAULT.readers_of_dataset(key), key
            assert "objection_playbook" in _features_for_dataset(key), key

    def test_source_follows_the_data_as_it_arrives(self, pipe):
        h = pipe
        acct = h.account()
        h.add_file(acct, "firmographics", FIRMO_CSV)
        h.add_file(acct, "technographics", TECHNO_HEADER)      # header only
        h.submit(acct)
        h.drain()
        source, cards = _source(h, acct)
        assert source == "none" and cards["status"] == "empty"

        # tech_breakdown arrives: the section goes stale, and the next run uses it.
        stale = [n["node_id"] for n in h.upload(acct, "tech_breakdown", BREAKDOWN_CSV)]
        assert stale == ["objection"]
        h.submit(acct)
        h.drain()
        source, cards = _source(h, acct)
        assert source == "tech_breakdown" and cards["status"] == "available"
        assert all(c["detected_vendors"] == [] for c in cards["data"]["cards"])

        # A new tech_breakdown naming a vendor is picked up, not served from cache.
        assert [n["node_id"] for n in h.upload(acct, "tech_breakdown", BREAKDOWN_CSV_V2)] == ["objection"]
        h.submit(acct)
        h.drain()
        _, cards = _source(h, acct)
        collab = next(c for c in cards["data"]["cards"] if c["area"] == "Collaboration")
        assert collab["detected_vendors"] == ["Zoom"]

        # Real technographics arrives later: it takes priority from the next run.
        assert [n["node_id"] for n in h.upload(acct, "technographics", TECHNO_CSV)] == ["objection"]
        h.submit(acct)
        h.drain()
        source, cards = _source(h, acct)
        assert source == "technographics"
        assert "fallback_note" not in cards["data"]
        assert all(c["evidence"].startswith("technographics -> ")
                   for c in cards["data"]["cards"])

    def test_a_fallback_is_visible_in_the_admin_data_gaps(self, pipe):
        from app.services.regen import data_gaps

        h = pipe
        acct = h.account()
        h.add_file(acct, "firmographics", FIRMO_CSV)
        h.add_file(acct, "tech_breakdown", BREAKDOWN_CSV)
        h.submit(acct)
        h.drain()
        ctx = h.widget(acct, "objection_incumbent_context")
        gaps = data_gaps.collect("objection_incumbent_context", ctx)
        codes = {g["code"] for g in gaps}
        assert data_gaps.FALLBACK_SOURCE in codes
        no_vendor = [g for g in gaps if g["code"] == data_gaps.NOT_IN_SOURCE]
        assert no_vendor and all("tech_breakdown" in g["reason"] for g in no_vendor)
