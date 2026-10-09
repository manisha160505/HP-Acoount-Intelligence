"""Evidence links that do not open are found, recorded, and reported.

The client, 7 Oct: a source is shown only when it has a link that opens. The
dashboard hides what `/unreachable-links` lists, so these tests hold the two
lines that decide what a seller sees:

  * only a DEFINITE failure is DEAD. A 403, a 429 or a timeout is UNSURE and
    stays visible - many publishers refuse scripts and open in a browser;
  * an account is told only about its own links.

Run: python -m pytest tests/test_link_health.py -v
"""

import os
import sys
from types import SimpleNamespace as NS

import pytest
import requests
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.core import deps
from app.database import mongodb
from app.services.hp import link_health
from app.services.regen.graph import DEFAULT as GRAPH
from app.services.regen.state import COLLECTION as STATE, state_id
from regen_fakes import FakeDb

USER = {"id": "u1", "email": "user@example.com", "full_name": "User", "role": "user"}


# --- check -----------------------------------------------------------------

def _fake_get(monkeypatch, outcome):
    """requests.get answering with `outcome`: (status, final url) or an exception."""
    def get(url, **_kw):
        if isinstance(outcome, Exception):
            raise outcome
        status, final = outcome
        return NS(status_code=status, url=final or url, close=lambda: None)
    monkeypatch.setattr(link_health.requests, "get", get)


ARTICLE = "https://news.example.com/2026/09/acme-opens-plant"


@pytest.mark.parametrize("outcome, verdict", [
    ((200, None), link_health.OK),
    ((404, None), link_health.DEAD),
    ((410, None), link_health.DEAD),
    ((200, "https://www8.hp.com/pagenotfound.html"), link_health.DEAD),
    ((200, "https://news.example.com/"), link_health.DEAD),      # retired to home page
    ((403, None), link_health.UNSURE),
    ((429, None), link_health.UNSURE),
    ((503, None), link_health.UNSURE),
    (requests.exceptions.ReadTimeout("slow"), link_health.UNSURE),
    (requests.exceptions.ConnectionError("NameResolutionError: no such host"), link_health.DEAD),
    # A site that refuses the server's address can still open for the user.
    (requests.exceptions.ConnectionError("[Errno 111] Connection refused"), link_health.UNSURE),
    (requests.exceptions.ConnectionError("Connection reset by peer"), link_health.UNSURE),
])
def test_only_a_definite_failure_is_dead(monkeypatch, outcome, verdict):
    _fake_get(monkeypatch, outcome)
    assert link_health.check(ARTICLE)[0] == verdict


def test_a_locale_root_folding_to_the_home_page_is_not_dead(monkeypatch):
    _fake_get(monkeypatch, (200, "https://www.example.com/"))
    assert link_health.check("https://www.example.com/en")[0] == link_health.OK


def test_a_removed_video_is_dead_though_youtube_answers_200(monkeypatch):
    _fake_get(monkeypatch, (404, None))   # the oEmbed answer
    assert link_health.check("https://youtu.be/abc")[0] == link_health.DEAD


# --- which links ---------------------------------------------------------------

def test_only_link_fields_are_collected():
    data = {
        "signals": [{"source_url": "https://a.example/x",
                     "resolved_source_url": "https://b.example/y",
                     "supporting_sources": [{"url": "https://c.example/z"}]}],
        "card": {"hp_proof_point_detail": {"source_url": "https://h20195.www2.hp.com/d"}},
        "play": {"hp_resource_url": "https://www.hp.com/workstations"},
        "contact": {"linkedin_url": "https://linkedin.com/in/someone",
                    "website": "https://acme.example"},
        "row": {"source_url": "uploaded_contacts.csv", "url": ""},
    }
    assert link_health.urls_in(data) == {
        "https://a.example/x", "https://b.example/y", "https://c.example/z",
        "https://h20195.www2.hp.com/d", "https://www.hp.com/workstations"}


# --- one account's dead links ---------------------------------------------------------

def _account(db, links_in_feed, links_in_output=()):
    account_id = str(ObjectId())
    db["accounts"].insert_one({"_id": ObjectId(account_id), "name": account_id})
    owner = GRAPH.owner["news_signals_feed"]
    db[STATE].insert_one({"_id": state_id(account_id, owner), "current": {"widgets": {
        "news_signals_feed": {"status": "available",
                              "data": {"signals": [{"source_url": u} for u in links_in_feed]}}}}})
    if links_in_output:
        db["account_widgets"].insert_one({
            "account_id": account_id, "widget_key": "content_generated_assets",
            "data": {"evidence": [{"source_url": u} for u in links_in_output]}})
    return account_id


def _verdict(db, url, verdict):
    link_health.record(db, url, (verdict, 404 if verdict == link_health.DEAD else 200, url, ""))


def test_an_account_hears_only_about_its_own_dead_links():
    db = FakeDb()
    mine = _account(db, ["https://a.example/dead", "https://a.example/fine",
                         "https://a.example/unsure", "https://a.example/never-checked"],
                    links_in_output=["https://a.example/dead-in-output"])
    _account(db, ["https://other.example/dead"])
    _verdict(db, "https://a.example/dead", link_health.DEAD)
    _verdict(db, "https://a.example/dead-in-output", link_health.DEAD)
    _verdict(db, "https://a.example/fine", link_health.OK)
    _verdict(db, "https://a.example/unsure", link_health.UNSURE)
    _verdict(db, "https://other.example/dead", link_health.DEAD)

    assert link_health.unreachable(db, mine) == [
        "https://a.example/dead", "https://a.example/dead-in-output"]


def test_a_recheck_replaces_the_verdict():
    db = FakeDb()
    acct = _account(db, ["https://a.example/back"])
    _verdict(db, "https://a.example/back", link_health.DEAD)
    _verdict(db, "https://a.example/back", link_health.OK)
    assert link_health.unreachable(db, acct) == []
    assert db[link_health.COLLECTION].count_documents({}) == 1


# --- the route ---------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(mongodb.db_instance, "db", db)
    from app.api.v1.account_data import router as data_router
    app = FastAPI()
    app.include_router(data_router, prefix="/api/v1")
    app.dependency_overrides[deps.require_user_role] = lambda: USER
    return TestClient(app), db


def test_the_route_lists_the_accounts_dead_links(client):
    c, db = client
    acct = _account(db, ["https://a.example/dead", "https://a.example/fine"])
    _verdict(db, "https://a.example/dead", link_health.DEAD)
    r = c.get("/api/v1/accounts/%s/data/unreachable-links" % acct)
    assert r.status_code == 200
    assert r.json() == {"unreachable": ["https://a.example/dead"]}


def test_the_route_refuses_a_bad_or_unknown_account(client):
    c, _db = client
    assert c.get("/api/v1/accounts/not-an-id/data/unreachable-links").status_code == 400
    assert c.get("/api/v1/accounts/%s/data/unreachable-links" % ObjectId()).status_code == 404


def test_sec_is_asked_with_a_declared_contact_and_nobody_else_is(monkeypatch):
    monkeypatch.setattr(link_health.settings, "LINK_CHECK_CONTACT", "ops@example.com")
    sec = link_health._headers("https://www.sec.gov/Archives/edgar/data/1/x.htm")
    assert sec["User-Agent"] == "HP Account Intelligence link check ops@example.com"
    assert link_health._headers(ARTICLE) is link_health.HEADERS


def test_without_a_contact_sec_gets_the_browser_headers(monkeypatch):
    monkeypatch.setattr(link_health.settings, "LINK_CHECK_CONTACT", "")
    assert link_health._headers("https://www.sec.gov/x") is link_health.HEADERS
