"""Only verified links are clickable (client-approved, 21 Oct).

Four things hold that rule up, and each is tested here with the network faked
(httpx.MockTransport) - no test makes a real request:

  * the verdict: what counts as broken, and what is deliberately kept;
  * which values in a widget are links (`collect_urls`);
  * the read path: a link recorded broken is gone from the GET response, a link
    never checked is kept, and a failed lookup leaves the response unchanged;
  * scripts/check_links.py: a dry run requests and writes nothing, --apply
    records verdicts and refuses the wrong database.

Run: python -m pytest tests/test_links.py -v
"""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import deps
from app.database import mongodb
from app.services import links
from app.services.links import checker as check_mod, collect, store as link_store
from app.services.regen import store as widget_store
from regen_fakes import FakeDb

ARTICLE = "https://news.example.com/2026/10/acme-opens-plant"
HTML = {"content-type": "text/html; charset=utf-8"}


# --- a fake network ----------------------------------------------------------

class Net:
    """Answers by URL. A route is a list of answers used in turn (the last one
    repeats): a status, (status, headers, body), or an exception to raise."""

    def __init__(self, routes):
        self.routes = {k: v if isinstance(v, list) else [v] for k, v in routes.items()}
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append((request.method, url))
        answers = self.routes.get(url)
        if answers is None:
            raise AssertionError("unexpected request %s %s" % (request.method, url))
        n = sum(1 for _m, u in self.calls if u == url) - 1
        answer = answers[min(n, len(answers) - 1)]
        if callable(answer) and not isinstance(answer, type):
            answer = answer(request)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):
            answer = (answer, HTML, "<html><title>Acme opens a plant</title></html>")
        status, headers, body = answer
        return httpx.Response(status, headers=headers, text=body, request=request)


def checker(routes, insecure_routes=None):
    net = Net(routes)
    insecure = Net(insecure_routes) if insecure_routes is not None else None
    sleeps = []
    c = links.Checker(transport=httpx.MockTransport(net),
                      insecure_transport=httpx.MockTransport(insecure) if insecure else None,
                      sleep=sleeps.append)
    c.net, c.insecure_net, c.sleeps = net, insecure, sleeps
    return c


def redirect(to, status=301):
    return (status, {"location": to}, "")


def page(title, status=200):
    return (status, HTML, "<html><head><title>%s</title></head><body>x</body></html>" % title)


def conn_error(message):
    def raise_it(request):
        return httpx.ConnectError(message, request=request)
    return raise_it


def timeout(request):
    return httpx.ReadTimeout("timed out", request=request)


# --- verdicts: status classes ------------------------------------------------

@pytest.mark.parametrize("status, ok, reason", [
    (200, True, "ok"),
    (204, True, "ok"),
    (401, True, "access_restricted"),     # paywall
    (403, True, "access_restricted"),     # refuses scripts
    (429, True, "access_restricted"),     # rate limited
    (404, False, "not_found"),
    (410, False, "gone"),
    # Any other 4xx refuses the request rather than saying the page is gone
    # (21 Oct: Bangkok Post 451, Betagro 405, USA Today 406 - all open in a
    # browser), so the link is kept.
    (400, True, "unverified_client_error"),
    (402, True, "unverified_client_error"),
    (405, True, "unverified_client_error"),
    (406, True, "unverified_client_error"),
    (451, True, "unverified_client_error"),
    (999, True, "unverified_status"),
])
def test_status_classes(status, ok, reason):
    c = checker({ARTICLE: status})
    v = c.check(ARTICLE)
    assert (v.ok, v.reason, v.status) == (ok, reason, status)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_a_5xx_is_retried_once_and_kept_when_it_persists(status):
    # A server error says nothing about the page; a site that errors for a
    # cloud address can open in a browser.
    c = checker({ARTICLE: [status, status, status]})
    v = c.check(ARTICLE)
    assert (v.ok, v.reason, v.status) == (True, "unverified_server_error", status)
    assert c.sleeps == [check_mod.RETRY_DELAY]
    assert [m for m, _u in c.net.calls] == ["HEAD", "GET", "GET"]


def test_a_5xx_that_turns_into_a_404_is_broken():
    c = checker({ARTICLE: [503, 503, 404]})
    assert (c.check(ARTICLE).ok, c.check(ARTICLE).reason) == (False, "not_found")


def test_a_5xx_that_recovers_is_ok():
    c = checker({ARTICLE: [503, 503, 200]})
    assert c.check(ARTICLE).ok


def test_head_then_get_the_get_decides():
    # A server that rejects HEAD (405) or answers it 404 is judged on its GET.
    for head in (405, 404, 501):
        c = checker({ARTICLE: [head, 200]})
        v = c.check(ARTICLE)
        assert v.ok and v.reason == "ok", head
        assert [m for m, _u in c.net.calls] == ["HEAD", "GET"]


def test_a_pdf_answered_by_head_needs_no_get():
    pdf = "https://ir.example.com/reports/annual-2025.pdf"
    c = checker({pdf: (200, {"content-type": "application/pdf"}, "")})
    assert c.check(pdf).ok
    assert [m for m, _u in c.net.calls] == ["HEAD"]


def test_redirects_are_followed_to_the_final_page():
    moved = "https://news.example.com/articles/acme-opens-plant"
    c = checker({ARTICLE: redirect(moved), moved: 200})
    v = c.check(ARTICLE)
    assert v.ok and v.final_url == moved


def test_a_redirect_loop_is_broken_and_a_long_chain_is_not():
    a, b = "https://x.example.com/a/b", "https://x.example.com/c/d"
    v = checker({a: redirect(b), b: redirect(a)}).check(a)
    assert (v.ok, v.reason) == (False, "redirect_loop")

    hops = ["https://y.example.com/p/%d" % i for i in range(8)]
    routes = {hops[i]: redirect(hops[i + 1]) for i in range(7)}
    routes[hops[7]] = 200
    v = checker(routes).check(hops[0])
    assert (v.ok, v.reason) == (True, "unverified_redirect_limit")


# --- verdicts: soft 404 ------------------------------------------------------

@pytest.mark.parametrize("title", [
    "404", "404 Not Found", "Error 404", "404 - Page Not Found", "Page Not Found | Reuters",
    "Not Found", "Error", "Error | Nikkei Asia", "Oops! That page can’t be found.",
    "The page you requested does not exist", "Sorry, this page could not be found",
    "Page not found – Acme Corp",
])
def test_a_title_that_says_not_found_is_a_soft_404(title):
    c = checker({ARTICLE: [200, page(title)]})
    v = c.check(ARTICLE)
    assert (v.ok, v.reason) == (False, "soft_404_title"), title


@pytest.mark.parametrize("title", [
    "Acme opens a plant in Penang",
    "Error rates fall at Acme's new plant",
    "Acme ships 404 new units in Q3",
    "Top 10 errors CIOs make with cloud",
    "Found: the missing link in supply chains",
    "Not found in translation: why HP localises",
    "",
])
def test_an_ordinary_title_is_not_a_soft_404(title):
    c = checker({ARTICLE: [200, page(title)]})
    assert c.check(ARTICLE).ok, title


def test_a_page_without_a_title_is_ok():
    c = checker({ARTICLE: [200, (200, HTML, "<html><body>no title</body></html>")]})
    assert c.check(ARTICLE).ok


def test_redirect_to_a_not_found_page_is_a_soft_404():
    hp = "https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA7-1694ENW"
    nf = "https://www8.hp.com/us/en/pagenotfound.html"
    v = checker({hp: redirect(nf, 302), nf: 200}).check(hp)
    assert (v.ok, v.reason) == (False, "soft_404_redirect")


def test_a_deep_link_retired_to_the_home_page_is_broken_but_a_locale_root_is_not():
    home = "https://news.example.com/"
    v = checker({ARTICLE: redirect(home), home: 200}).check(ARTICLE)
    assert (v.ok, v.reason) == (False, "redirect_to_home")

    en, root = "https://www.example.com/en", "https://www.example.com/"
    assert checker({en: redirect(root), root: 200}).check(en).ok


def test_only_the_first_50kb_is_read_for_the_title():
    late = "<html>" + "x" * 60_000 + "<title>Page not found</title></html>"
    c = checker({ARTICLE: [200, (200, HTML, late)]})
    assert c.check(ARTICLE).ok


# --- verdicts: transport failures ---------------------------------------------

@pytest.mark.parametrize("make, ok, reason", [
    (conn_error("[Errno -2] Name or service not known"), False, "dns_failure"),
    (conn_error("[Errno 8] nodename nor servname provided, or not known"), False, "dns_failure"),
    (conn_error("[Errno -3] Temporary failure in name resolution"), True,
     "unverified_dns_temporary"),
    (conn_error("[Errno -5] No address associated with hostname"), False, "dns_failure"),
    (conn_error("[Errno 111] Connection refused"), True, "unverified_connection_refused"),
    (conn_error("[Errno 61] Connection refused"), True, "unverified_connection_refused"),
    (conn_error("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "certificate has expired (_ssl.c:1006)"), False, "ssl_error"),
    (conn_error("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "self-signed certificate (_ssl.c:1006)"), False, "ssl_error"),
    (conn_error("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "self signed certificate in certificate chain (_ssl.c:1006)"), False,
     "ssl_error"),
    (conn_error("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "Hostname mismatch, certificate is not valid for 'x.example.com'. "
                "(_ssl.c:1006)"), False, "ssl_error"),
    # A handshake a site breaks off - how some turn away a cloud address.
    (conn_error("[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] sslv3 alert handshake failure "
                "(_ssl.c:1006)"), True, "unverified_tls_error"),
    (conn_error("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of "
                "protocol (_ssl.c:1006)"), True, "unverified_tls_error"),
    (conn_error("[Errno 101] Network is unreachable"), True, "unverified_connect_error"),
    (lambda r: httpx.RemoteProtocolError("Server disconnected", request=r), True,
     "unverified_connection_dropped"),
    (lambda r: httpx.ReadError("Connection reset by peer", request=r), True,
     "unverified_connection_dropped"),
])
def test_transport_failures(make, ok, reason):
    c = checker({ARTICLE: make})
    v = c.check(ARTICLE)
    assert (v.ok, v.reason) == (ok, reason)


@pytest.mark.parametrize("make", [conn_error("[Errno -2] Name or service not known"),
                                  conn_error("[Errno 111] Connection refused")])
def test_a_failure_on_head_a_get_would_repeat_is_not_asked_again(make):
    c = checker({ARTICLE: make})
    c.check(ARTICLE)
    assert [m for m, _u in c.net.calls] == ["HEAD"]


def test_a_timeout_is_retried_once_then_kept():
    # A slow site is not a missing one.
    c = checker({ARTICLE: timeout})
    v = c.check(ARTICLE)
    assert (v.ok, v.reason) == (True, "unverified_timeout")
    assert [m for m, _u in c.net.calls] == ["HEAD", "GET", "GET"]
    assert len(c.sleeps) == 1


def test_a_timeout_that_turns_into_a_404_is_broken():
    c = checker({ARTICLE: [timeout, timeout, 404]})
    assert (c.check(ARTICLE).ok, c.check(ARTICLE).reason) == (False, "not_found")


def test_a_timeout_that_recovers_is_ok():
    c = checker({ARTICLE: [timeout, timeout, 200]})
    assert c.check(ARTICLE).ok


def test_an_incomplete_certificate_chain_is_retried_unverified():
    incomplete = conn_error("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                            "unable to get local issuer certificate (_ssl.c:1006)")
    hp = "https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA8-0001ENW"
    c = checker({hp: incomplete}, insecure_routes={hp: [200, page("Acme case study")]})
    v = c.check(hp)
    assert (v.ok, v.reason) == (True, "ok_unverified_tls")

    c = checker({hp: incomplete}, insecure_routes={hp: 404})
    assert (c.check(hp).ok, c.check(hp).reason) == (False, "not_found")


@pytest.mark.parametrize("url", ["", "not a url", "https://", "ftp://files.example.com/a",
                                 "https://exa mple.com/x", "https://localhost/x",
                                 "https://example.com:notaport/x"])
def test_an_invalid_url_is_broken_without_a_request(url):
    c = checker({})
    v = c.check(url)
    assert (v.ok, v.reason) == (False, "invalid_url")
    assert c.net.calls == []


# --- verdicts: special hosts -----------------------------------------------------

GN = "https://news.google.com/rss/articles/CBMiXmh0dHBzOi8vd3d3?oc=5"


@pytest.mark.parametrize("answer", [200, redirect("https://consent.google.com/m?x=1", 302)])
def test_news_google_answering_is_ok_and_not_followed(answer):
    c = checker({GN: answer})
    v = c.check(GN)
    assert (v.ok, v.reason) == (True, "news_google")
    assert c.net.calls == [("GET", GN)]


def test_news_google_404_is_broken():
    v = checker({GN: 404}).check(GN)
    assert (v.ok, v.reason) == (False, "not_found")


LI = "https://www.linkedin.com/in/jane-doe-123"


@pytest.mark.parametrize("answer", [999, 403, 429, 503, timeout,
                                    conn_error("[Errno 111] Connection refused")])
def test_linkedin_is_ok_whatever_it_answers_a_script(answer):
    v = checker({LI: answer}).check(LI)
    assert v.ok


@pytest.mark.parametrize("answer, reason", [
    (404, "not_found"),
    (conn_error("[Errno -2] Name or service not known"), "dns_failure"),
])
def test_linkedin_is_broken_on_a_real_404_or_dns(answer, reason):
    v = checker({LI: answer}).check(LI)
    assert (v.ok, v.reason) == (False, reason)


def test_linkedin_soft_404_title_is_not_trusted():
    v = checker({LI: [200, page("Page not found | LinkedIn")]}).check(LI)
    assert v.ok


def test_a_removed_youtube_video_is_broken_though_youtube_answers_200():
    vid = "https://youtu.be/abc123"
    oembed = "https://www.youtube.com/oembed?format=json&url=https%3A%2F%2Fyoutu.be%2Fabc123"
    for status in (400, 404):
        v = checker({oembed: status}).check(vid)
        assert (v.ok, v.reason) == (False, "video_removed"), status
    assert checker({oembed: 200}).check(vid).ok
    # Private or not embeddable: may still play on YouTube, so it is kept.
    v = checker({oembed: 401}).check(vid)
    assert (v.ok, v.reason) == (True, "unverified_video_restricted")
    assert checker({oembed: 503}).check(vid).ok
    assert checker({oembed: timeout}).check(vid).ok


def test_the_browser_user_agent_is_sent():
    seen = {}

    def capture(request):
        seen["ua"] = request.headers.get("user-agent")
        return 200
    checker({ARTICLE: capture}).check(ARTICLE)
    assert seen["ua"].startswith("Mozilla/5.0")


# --- collect_urls ----------------------------------------------------------------

NEWS_FEED = {
    "signals": [{
        "signal_id": "s1",
        "headline": "Acme opens a plant - see https://inline.example.com/x for more",
        "source_url": GN,
        "resolved_source_url": ARTICLE,
        "supporting_sources": [{"url": "https://b.example.com/y", "publisher": "B"},
                               {"url": "https://c.example.com/z"}],
        "hp_proof_point": {"text": "HP helped", "source_url": "https://h20195.www2.hp.com/d"},
    }],
}
CONTACTS = {"contacts": [
    {"full_name": "Jane", "linkedin_url": "www.linkedin.com/in/jane", "email": "j@acme.com"},
    {"full_name": "Raj", "linkedin_url": "https://linkedin.com/in/raj"},
    {"full_name": "Ann", "linkedin_url": ""},
]}
EXEC = {"company_name": "Acme", "domain": "acme.com", "industry": "Software",
        "parent_company": "Acme Holdings"}
TECH = {"full_tech_stack": ["Microsoft Azure", "Dell Latitude"],
        "categories": [{"domain": "Cloud Security", "evidence": [
            {"source_url": "uploaded_technographics.csv", "label": "Technographics"},
            {"url": "https://builtwith.example.com/acme.com"}]}]}
PLAYS = {"plays": [{"hp_resource_url": "https://www.hp.com/workstations",
                    "hp_resource": {"url": "https://www.hp.com/z-series", "label": "Z"},
                    "urls": ["https://d.example.com/1", "not-a-link"]}]}


def test_collect_urls_on_representative_widgets():
    assert set(links.collect_urls(NEWS_FEED)) == {
        GN, ARTICLE, "https://b.example.com/y", "https://c.example.com/z",
        "https://h20195.www2.hp.com/d"}
    assert set(links.collect_urls(CONTACTS)) == {
        "https://www.linkedin.com/in/jane", "https://linkedin.com/in/raj"}
    assert set(links.collect_urls(EXEC)) == {"https://acme.com"}
    assert set(links.collect_urls(TECH)) == {"https://builtwith.example.com/acme.com"}
    assert set(links.collect_urls(PLAYS)) == {
        "https://www.hp.com/workstations", "https://www.hp.com/z-series",
        "https://d.example.com/1"}


def test_collect_urls_yields_each_link_once_and_skips_hosted_copies():
    own_copy = next(iter(collect.KEEP))
    data = {"a": [{"url": ARTICLE}, {"url": ARTICLE}], "b": {"source_url": own_copy}}
    assert list(links.collect_urls(data)) == [ARTICLE]


def test_collect_urls_tolerates_any_shape():
    assert list(links.collect_urls(None)) == []
    assert list(links.collect_urls({"n": 3, "x": None, "y": [1, 2.5, True]})) == []


# --- strip_broken ---------------------------------------------------------------

def test_a_broken_primary_source_blanks_the_whole_chain():
    # resolved_source_url is what the dashboard opens; blanking it alone would
    # fall through to the news.google.com redirect to the same dead article.
    out = links.strip_broken(NEWS_FEED, {ARTICLE})
    s = out["signals"][0]
    assert s["resolved_source_url"] == "" and s["source_url"] == ""
    assert s["headline"] == NEWS_FEED["signals"][0]["headline"]
    assert NEWS_FEED["signals"][0]["resolved_source_url"] == ARTICLE     # not mutated


def test_a_broken_fallback_does_not_blank_a_working_primary():
    out = links.strip_broken(NEWS_FEED, {GN})
    s = out["signals"][0]
    assert s["resolved_source_url"] == ARTICLE and s["source_url"] == ""


def test_a_list_entry_that_is_only_a_broken_link_is_removed():
    out = links.strip_broken(NEWS_FEED, {"https://c.example.com/z", "https://b.example.com/y"})
    sources = out["signals"][0]["supporting_sources"]
    # The entry with a publisher stays (with no link, so it renders nothing
    # clickable); the bare-link entry is dropped.
    assert sources == [{"url": "", "publisher": "B"}]

    out = links.strip_broken(PLAYS, {"https://d.example.com/1"})
    assert out["plays"][0]["urls"] == ["not-a-link"]


def test_scheme_less_links_are_stripped_by_the_url_the_browser_opens():
    out = links.strip_broken(CONTACTS, {"https://www.linkedin.com/in/jane"})
    assert out["contacts"][0]["linkedin_url"] == ""
    assert out["contacts"][1]["linkedin_url"] == "https://linkedin.com/in/raj"
    out = links.strip_broken(EXEC, {"https://acme.com"})
    assert out["domain"] == "" and out["company_name"] == "Acme"


def test_nothing_broken_returns_the_same_object():
    assert links.strip_broken(NEWS_FEED, set()) is NEWS_FEED


# --- store ------------------------------------------------------------------------

def test_broken_urls_is_one_query_and_unknown_urls_are_kept():
    db = FakeDb()
    link_store.record(db, links.Verdict("https://a.example.com/dead", False, 404, "not_found"))
    link_store.record(db, links.Verdict("https://a.example.com/fine", True, 200, "ok"))
    calls = []
    real_find = db[link_store.COLLECTION].find
    db[link_store.COLLECTION].find = lambda *a, **k: calls.append(1) or real_find(*a, **k)
    got = link_store.broken_urls(db, ["https://a.example.com/dead", "https://a.example.com/fine",
                                      "https://a.example.com/never-checked"])
    assert got == {"https://a.example.com/dead"}
    assert calls == [1]
    assert link_store.broken_urls(db, []) == set()


def test_a_recheck_replaces_the_verdict():
    db = FakeDb()
    url = "https://a.example.com/back"
    link_store.record(db, links.Verdict(url, False, 404, "not_found"))
    link_store.record(db, links.Verdict(url, True, 200, "ok"))
    assert link_store.broken_urls(db, [url]) == set()
    row = db[link_store.COLLECTION].find_one({"_id": url})
    assert row["ok"] is True and row["status"] == 200 and row["checked_at"]
    assert db[link_store.COLLECTION].count_documents({}) == 1


# --- the read path ----------------------------------------------------------------

USER = {"id": "u1", "email": "user@example.com", "full_name": "User", "role": "user"}


@pytest.fixture
def api(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(mongodb.db_instance, "db", db)
    from app.api.v1.widgets import router as widgets_router
    app = FastAPI()
    app.include_router(widgets_router, prefix="/api/v1")
    for dep in (deps.require_user_role, deps.require_account_access):
        app.dependency_overrides[dep] = lambda: USER
    account_id = str(ObjectId())
    db["accounts"].insert_one({"_id": ObjectId(account_id), "name": "Acme"})
    widget_store.put(account_id, "news_signals_feed",
                     {"status": "available", "data": NEWS_FEED}, db=db)
    return TestClient(app), db, account_id


def _feed(client, account_id):
    resp = client.get("/api/v1/accounts/%s/widgets/recent_news_signals" % account_id)
    assert resp.status_code == 200
    return next(w for w in resp.json() if w["widget_key"] == "news_signals_feed")["data"]


def test_the_read_path_removes_broken_links_and_keeps_unknown_ones(api):
    client, db, acct = api
    link_store.record(db, links.Verdict(ARTICLE, False, 404, "not_found"))
    link_store.record(db, links.Verdict("https://b.example.com/y", True, 200, "ok"))
    s = _feed(client, acct)["signals"][0]
    assert s["resolved_source_url"] == "" and s["source_url"] == ""
    # Recorded ok, and never checked: both kept.
    assert [x["url"] for x in s["supporting_sources"]] == [
        "https://b.example.com/y", "https://c.example.com/z"]
    assert s["hp_proof_point"]["source_url"] == "https://h20195.www2.hp.com/d"


def test_the_read_path_without_any_verdicts_returns_the_widget_as_stored(api):
    client, _db, acct = api
    assert _feed(client, acct) == NEWS_FEED


def test_the_read_path_makes_one_lookup_per_response(api, monkeypatch):
    client, _db, acct = api
    calls = []
    real = links.broken_urls
    monkeypatch.setattr(links, "broken_urls", lambda db, urls: calls.append(set(urls))
                        or real(db, urls))
    _feed(client, acct)
    assert len(calls) == 1 and ARTICLE in calls[0]


def test_a_failed_lookup_returns_the_widget_unchanged(api, monkeypatch):
    client, db, acct = api
    link_store.record(db, links.Verdict(ARTICLE, False, 404, "not_found"))

    def boom(*_a, **_k):
        raise RuntimeError("link_checks unavailable")
    monkeypatch.setattr(links, "broken_urls", boom)
    assert _feed(client, acct) == NEWS_FEED


# --- scripts/check_links.py ----------------------------------------------------------

def _script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "check_links.py"
    spec = importlib.util.spec_from_file_location("check_links_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeChecker:
    def __init__(self, broken=()):
        self.broken, self.checked = set(broken), []

    def check(self, url):
        self.checked.append(url)
        if url in self.broken:
            return links.Verdict(url, False, 404, "not_found", url)
        return links.Verdict(url, True, 200, "ok", url)


@pytest.fixture
def script_db():
    db = FakeDb()
    for name, data in (("Acme", NEWS_FEED), ("Beta", {"signals": [{"source_url": ARTICLE}]})):
        account_id = str(ObjectId())
        db["accounts"].insert_one({"_id": ObjectId(account_id), "name": name})
        widget_store.put(account_id, "news_signals_feed",
                         {"status": "available", "data": data}, db=db)
    # A user output, read from account_widgets.
    db["account_widgets"].insert_one({"account_id": account_id,
                                      "widget_key": "content_generated_assets",
                                      "data": {"evidence": [{"source_url":
                                                             "https://e.example.com/out"}]}})
    return db


ALL_URLS = {GN, ARTICLE, "https://b.example.com/y", "https://c.example.com/z",
            "https://h20195.www2.hp.com/d", "https://e.example.com/out"}


def test_gather_reads_committed_widgets_and_user_outputs(script_db):
    shown = _script().gather(script_db)
    assert set(shown) == ALL_URLS
    assert shown[ARTICLE] == {"Acme", "Beta"}


def test_a_dry_run_checks_and_writes_nothing(script_db, capsys):
    fake = FakeChecker()
    assert _script().main([], db=script_db, checker=fake) == 0
    assert fake.checked == []
    assert script_db[link_store.COLLECTION].count_documents({}) == 0
    out = capsys.readouterr().out
    assert "Database:" in out and "6 to check" in out and "Nothing was checked" in out


def test_apply_refuses_the_wrong_database(script_db, capsys):
    fake = FakeChecker()
    assert _script().main(["--apply", "--target-db", "some_other_db"],
                          db=script_db, checker=fake) == 2
    assert fake.checked == []
    assert "Refusing" in capsys.readouterr().err


def test_apply_records_verdicts_and_skips_fresh_ones(script_db, capsys):
    from app.config.settings import settings
    mod = _script()
    args = ["--apply", "--target-db", settings.DB_NAME, "--host-delay", "0"]

    fake = FakeChecker(broken={ARTICLE})
    assert mod.main(args, db=script_db, checker=fake) == 0
    assert set(fake.checked) == ALL_URLS
    assert link_store.broken_urls(script_db, ALL_URLS) == {ARTICLE}
    out = capsys.readouterr().out
    assert "1 broken" in out and "not_found" in out and "news.example.com" in out

    # Checked a moment ago: nothing to do.
    again = FakeChecker()
    mod.main(args, db=script_db, checker=again)
    assert again.checked == []

    # Older than --days, or --recheck-all: checked again.
    old = datetime.now(UTC) - timedelta(days=8)
    script_db[link_store.COLLECTION].update_one({"_id": ARTICLE},
                                                {"$set": {"checked_at": old}})
    stale = FakeChecker()
    mod.main(args, db=script_db, checker=stale)
    assert stale.checked == [ARTICLE]
    assert link_store.broken_urls(script_db, ALL_URLS) == set()

    everything = FakeChecker()
    mod.main([*args, "--recheck-all"], db=script_db, checker=everything)
    assert set(everything.checked) == ALL_URLS


def test_the_host_limiter_runs_the_check():
    limiter = _script().HostLimiter(2, 0)
    assert limiter.run(ARTICLE, lambda u: u.upper()) == ARTICLE.upper()


def test_the_summary_separates_kept_unverified_links_from_broken_ones(capsys):
    verdicts = [links.Verdict(ARTICLE, False, 404, "not_found", ARTICLE),
                links.Verdict("https://b.example.com/y", True, None, "unverified_timeout"),
                links.Verdict("https://c.example.com/z", True, 503, "unverified_server_error"),
                links.Verdict("https://d.example.com/1", True, 403, "access_restricted"),
                links.Verdict("https://e.example.com/2", True, 200, "ok")]
    _script()._print_summary(verdicts, {ARTICLE: {"Acme"}})
    out = capsys.readouterr().out
    assert "Checked 5: 4 ok (2 kept, not verified), 1 broken (hidden)" in out
    assert "unverified_timeout" in out and "unverified_server_error" in out
    assert "access_restricted" in out
    assert "Broken (hidden) by reason:" in out and "Accounts showing a broken link: 1" in out
