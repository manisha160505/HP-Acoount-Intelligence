"""A filing's own PDF, opened from its evidence chip - and nothing else.

The client, 6 Oct: evidence sources must be clickable. A catalyst's evidence
reads `australia_post_2024-FY_annual_report.pdf p.11`, and the public URL for
that document is unreliable: of 481 filing URLs the crawl attempted, 116 failed
or returned something that was not a document. So the link opens the copy we
hold, at the cited page.

The half of this that needs pinning is what the route REFUSES. It is reachable
from a plain `<a href>` with the token in the query string, and it takes a
filename from the client, so these tests exist to hold two lines:

  * only `compliance_filings`, only `.pdf` - every other dataset holds the
    client's own records, and `prospect_contacts` holds names, emails and phone
    numbers;
  * the filename is a database lookup, never a path - so there is no traversal
    to defend against, and that property is asserted rather than assumed.

Run: python -m pytest tests/test_filing_view.py -v
"""

import os
import sys

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.api.v1.account_data import sanitize_filename
from app.core import deps
from app.database import mongodb
from regen_fakes import FakeDb

USER = {"id": "u1", "email": "user@example.com", "full_name": "User", "role": "user"}

AR = "australia_post_2024-FY_annual_report.pdf"
PDF_BYTES = b"%PDF-1.4\n% a filing\n"


@pytest.fixture
def env(monkeypatch, tmp_path):
    db = FakeDb()
    monkeypatch.setattr(mongodb.db_instance, "db", db)

    from app.api.v1.account_data import router as data_router
    from app.observability.envelope_middleware import ResponseEnvelopeMiddleware
    app = FastAPI()
    app.include_router(data_router, prefix="/api/v1")
    # Mounted deliberately. Without it the cache-control assertion below passes
    # for the wrong reason: this middleware stamps every /api/ response, and it
    # used to do so unconditionally - so the route's own header never survived
    # in the running app while the test said it did.
    app.add_middleware(ResponseEnvelopeMiddleware)
    for dep in (deps.require_admin_role, deps.get_current_user_flexible,
                deps.require_user_role, deps.require_user_role_flexible):
        app.dependency_overrides[dep] = lambda: USER

    account_id = str(ObjectId())
    db["accounts"].insert_one({"_id": ObjectId(account_id), "name": "Acme"})

    # The route resolves a row's own relative file_path through
    # datasets.find_file_path, whose first candidate is the working directory.
    monkeypatch.chdir(tmp_path)
    return TestClient(app), db, account_id, tmp_path


def _register(db, account_id, root, name, *, dataset="compliance_filings",
              on_disk=True, body=PDF_BYTES, status="active"):
    """One uploaded file, exactly as `upload_account_data` records it.

    `original_filename` keeps the name verbatim; the name ON DISK goes through
    the same `sanitize_filename` the upload applies, which is what keeps a
    filename containing a quote or a non-ASCII character writable at all. The
    two differing is the whole reason the route looks the file up by the
    registered name rather than by its path.
    """
    stored = "%s_123_%s" % (dataset, sanitize_filename(os.path.splitext(name)[0]))
    rel = "data/accounts/%s/%s/%s%s" % (
        account_id, dataset, stored, os.path.splitext(name)[1])
    if on_disk:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    db["account_data_files"].insert_one({
        "account_id": account_id,
        "dataset_key": dataset,
        "category": dataset,
        "original_filename": name,
        "stored_filename": os.path.basename(rel),
        "file_path": rel,
        "status": status,
    })


def _get(client, account_id, name):
    return client.get("/api/v1/accounts/%s/data/filing" % account_id,
                      params={"name": name})


class TestTheFilingOpens:

    def test_the_pdf_is_served_inline_as_a_pdf(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR)
        r = _get(client, acct, AR)
        assert r.status_code == 200
        assert r.content == PDF_BYTES
        assert r.headers["content-type"] == "application/pdf"
        # Inline, or the browser downloads it and `#page=` is never honoured.
        assert r.headers["content-disposition"].startswith("inline")
        assert AR in r.headers["content-disposition"]

    def test_only_one_content_disposition_header_is_sent(self, env):
        """Starlette writes this header itself from `filename=`. The older
        download route also passes one by hand, which is how you end up with
        two and an undefined winner."""
        client, db, acct, root = env
        _register(db, acct, root, AR)
        r = _get(client, acct, AR)
        sent = [v for k, v in r.headers.raw
                if k.decode().lower() == "content-disposition"]
        assert len(sent) == 1, sent

    def test_the_bytes_are_cacheable_but_not_shared(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR)
        assert "private" in _get(client, acct, AR).headers["cache-control"]

    def test_one_filing_of_several_is_addressed_by_name(self, env):
        """compliance_filings is a multi-file dataset, so several rows are
        active at once. This is the whole reason the dataset-level download
        route could not do this job - its find_one returns an arbitrary one."""
        client, db, acct, root = env
        _register(db, acct, root, "first.pdf", body=b"%PDF-1.4 first")
        _register(db, acct, root, "second.pdf", body=b"%PDF-1.4 second")
        assert _get(client, acct, "first.pdf").content == b"%PDF-1.4 first"
        assert _get(client, acct, "second.pdf").content == b"%PDF-1.4 second"


class TestTheHeadersSurviveTheMiddleware:
    """`ResponseEnvelopeMiddleware` stamps `no-store` on every `/api/` response.
    It used to assign unconditionally, which threw away whatever the handler
    decided - so a 20MB annual report was re-fetched on every single click."""

    def test_the_pdf_keeps_its_own_cache_policy(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR)
        cc = _get(client, acct, AR).headers["cache-control"]
        assert "private" in cc
        assert "no-store" not in cc

    def test_a_json_route_still_gets_no_store(self, env):
        """The middleware's own reason for existing: a regenerated widget must
        not be served from a browser's heuristic cache. Pinned so the guard
        change above cannot quietly disable it."""
        client, _db, acct, _root = env
        r = client.get("/api/v1/accounts/%s/data" % acct)
        assert r.status_code == 200
        assert "no-store" in r.headers["cache-control"]

    def test_the_pdf_body_is_not_enveloped(self, env):
        """The middleware wraps JSON. A PDF wrapped in an envelope is a corrupt
        file, so the early return for non-JSON content types is load-bearing."""
        client, db, acct, root = env
        _register(db, acct, root, AR)
        assert _get(client, acct, AR).content == PDF_BYTES

    def test_a_byte_range_still_works(self, env):
        """What makes `#page=250` of a large filing open quickly: the browser
        asks for the bytes it needs. Pinned because the middleware sits in the
        response path and could buffer the stream."""
        client, db, acct, root = env
        _register(db, acct, root, AR)
        r = client.get("/api/v1/accounts/%s/data/filing" % acct,
                       params={"name": AR}, headers={"Range": "bytes=0-7"})
        assert r.status_code == 206
        assert r.content == PDF_BYTES[:8]
        assert "content-range" in r.headers


class TestTheFilenameSurvivesTheHeader:

    def test_a_non_ascii_filename_does_not_break_the_response(self, env):
        """`original_filename` is stored verbatim, so it can be any text. Built
        by hand, this header raises UnicodeEncodeError in the ASGI layer and the
        request 500s; Starlette's own `filename=` encodes it per RFC 5987."""
        client, db, acct, root = env
        name = "日本語_report.pdf"
        _register(db, acct, root, name)
        r = _get(client, acct, name)
        assert r.status_code == 200
        assert r.content == PDF_BYTES

    def test_a_filename_with_a_quote_does_not_split_the_header(self, env):
        client, db, acct, root = env
        name = 'odd";name.pdf'
        _register(db, acct, root, name)
        r = _get(client, acct, name)
        assert r.status_code == 200
        sent = [v for k, v in r.headers.raw
                if k.decode().lower() == "content-disposition"]
        assert len(sent) == 1, sent


class TestWhatItRefuses:

    def test_another_dataset_is_refused_even_though_the_row_exists(self, env):
        """prospect_contacts carries names, emails and phone numbers. The route
        is reachable from a link, so this must not depend on the caller."""
        client, db, acct, root = env
        _register(db, acct, root, "prospect_contacts.csv",
                  dataset="prospect_contacts")
        assert _get(client, acct, "prospect_contacts.csv").status_code == 404

    def test_a_non_pdf_inside_the_filings_dataset_is_refused(self, env):
        """`_filings_index.csv` is uploaded into compliance_filings beside the
        PDFs. It is a list of documents, not a document."""
        client, db, acct, root = env
        _register(db, acct, root, "_filings_index.csv", body=b"company,url\n")
        assert _get(client, acct, "_filings_index.csv").status_code == 404

    @pytest.mark.parametrize("name", [
        "../../../etc/passwd",
        "../../../etc/passwd.pdf",
        "..\\..\\windows\\win.ini.pdf",
        "/etc/shadow.pdf",
        "data/accounts/other/compliance_filings/x.pdf",
    ])
    def test_a_path_is_not_a_filename(self, env, name):
        """The name is matched against the registry and never joined to a path,
        so a traversal attempt matches no row. Asserted because the property is
        the defence - there is no sanitiser to get wrong."""
        client, db, acct, root = env
        _register(db, acct, root, AR)
        assert _get(client, acct, name).status_code == 404

    def test_another_accounts_filing_is_not_reachable(self, env):
        client, db, acct, root = env
        other = str(ObjectId())
        db["accounts"].insert_one({"_id": ObjectId(other), "name": "Other"})
        _register(db, other, root, AR)
        assert _get(client, acct, AR).status_code == 404

    def test_a_replaced_row_is_not_served(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR, status="replaced")
        assert _get(client, acct, AR).status_code == 404

    def test_registered_but_not_on_this_machine_is_a_404_that_leaks_nothing(self, env):
        """The ordinary state of a developer checkout. The message must not
        describe where the file was expected."""
        client, db, acct, root = env
        _register(db, acct, root, AR, on_disk=False)
        r = _get(client, acct, AR)
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert "data/accounts" not in detail
        assert str(root) not in detail

    def test_an_unknown_filing_is_a_404(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR)
        assert _get(client, acct, "something_else.pdf").status_code == 404

    def test_a_missing_or_blank_name_is_a_404_not_a_crash(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR)
        assert _get(client, acct, "").status_code == 404
        assert client.get(
            "/api/v1/accounts/%s/data/filing" % acct).status_code == 422

    def test_a_malformed_account_id_is_rejected_before_any_lookup(self, env):
        client, _db, _acct, _root = env
        assert _get(client, "not-an-object-id", AR).status_code == 400

    def test_an_unknown_account_is_a_404(self, env):
        client, _db, _acct, _root = env
        assert _get(client, str(ObjectId()), AR).status_code == 404


class TestItIsNotOpenToAnySignedInPrincipal:

    def test_a_role_outside_user_and_admin_is_refused(self, env, monkeypatch):
        """The token may ride in the query string, which is what makes a plain
        link work - and `get_current_user_flexible` alone checks no role at all.
        The older download route still has that gap."""
        client, db, acct, root = env
        _register(db, acct, root, AR)
        client.app.dependency_overrides[deps.require_user_role_flexible] =             deps.require_user_role_flexible.__wrapped__             if hasattr(deps.require_user_role_flexible, "__wrapped__")             else (lambda: {"id": "x", "role": "viewer"})
        # Call the real check directly: the override above only proves the
        # dependency is wired, not what it decides.
        import pytest as _pytest
        from fastapi import HTTPException
        with _pytest.raises(HTTPException) as exc:
            deps.require_user_role_flexible({"id": "x", "role": "viewer"})
        assert exc.value.status_code == 403

    def test_the_route_depends_on_the_role_checked_dependency(self, env):
        """Wiring, asserted on the route itself so a future edit that drops back
        to the role-free dependency fails here."""
        from app.api.v1 import account_data as mod
        route = next(r for r in mod.router.routes
                     if getattr(r, "path", "").endswith("/filing"))
        names = [d.call.__name__ for d in route.dependant.dependencies]
        assert "require_user_role_flexible" in names


class TestWhichFileWhenTwoShareAName:

    def test_the_file_served_is_the_one_the_corpus_read(self, env):
        """compliance_filings is multi-file, so two active rows can carry one
        original_filename. `dataset_file_paths` returns them sorted, so the
        evidence quotes came from the first path - and a seller must open that
        same document, not an arbitrary one of the two."""
        client, db, acct, root = env
        rel_b = "data/accounts/%s/compliance_filings/zz_second.pdf" % acct
        rel_a = "data/accounts/%s/compliance_filings/aa_first.pdf" % acct
        for rel, body in ((rel_b, b"%PDF-1.4 second"), (rel_a, b"%PDF-1.4 first")):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            db["account_data_files"].insert_one({
                "account_id": acct, "dataset_key": "compliance_filings",
                "category": "compliance_filings", "original_filename": AR,
                "stored_filename": os.path.basename(rel), "file_path": rel,
                "status": "active"})
        assert _get(client, acct, AR).content == b"%PDF-1.4 first"


class TestTheJoinKeyIsWhatTheChipAlreadyShows:
    """The link is built from `filing_label`, which `priorities._source`
    publishes on every citation and which IS the registered
    `original_filename`. That is what makes this need no rebuild - so the
    equality is pinned here rather than left as a comment."""

    def test_the_label_on_an_evidence_row_is_the_name_the_route_accepts(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR)

        from app.services.dashboard.priorities import source_label
        row = {"filing_label": AR, "page": 11, "dataset": "compliance_filings"}
        assert source_label(row) == "%s p.11" % AR

        # The chip's label carries the page; the lookup uses the bare filename.
        assert _get(client, acct, row["filing_label"]).status_code == 200
def _manifest(client, account_id):
    return client.get("/api/v1/accounts/%s/data/filings" % account_id)


def _listed(response):
    """The manifest payload, out of the response envelope.

    `ResponseEnvelopeMiddleware` wraps every JSON response as
    `{success, data, error, meta}`, and the frontend's axios client unwraps it so
    a caller sees the payload directly. The middleware is mounted in this test's
    app, so the tests have to unwrap it the same way.
    """
    body = response.json()
    return (body.get("data") if isinstance(body, dict) and "data" in body else body)


class TestTheManifestNeverPromisesADeadLink:
    """Why this exists: the UI links a filing from its `filing_label`, which was
    true of the corpus when the widget was built, not necessarily now. A
    re-uploaded filing leaves its old row `replaced`, and a filing can be
    registered on an account whose PDF is not on this machine - in both cases the
    document route correctly refuses and an optimistic chip opens a tab with a
    404 in it. A dead link is worse than plain text, so the UI is told what it may
    link."""

    def test_it_lists_a_filing_that_can_be_opened(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR)
        body = _listed(_manifest(client, acct))
        assert body["filings"] == [{"filename": AR, "pages": None}]

    def test_the_page_count_comes_through(self, env):
        """`row_count` is the page count for a PDF, so the UI can tell whether a
        cited page is really in the document."""
        client, db, acct, root = env
        _register(db, acct, root, AR)
        db["account_data_files"].update_one(
            {"original_filename": AR}, {"$set": {"row_count": 148}})
        assert _listed(_manifest(client, acct))["filings"][0]["pages"] == 148

    def test_a_replaced_filing_is_not_listed(self, env):
        """The case that produced the dead link."""
        client, db, acct, root = env
        _register(db, acct, root, AR, status="replaced")
        assert _listed(_manifest(client, acct))["filings"] == []

    def test_a_filing_not_on_this_machine_is_not_listed(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR, on_disk=False)
        assert _listed(_manifest(client, acct))["filings"] == []

    def test_another_dataset_is_not_listed(self, env):
        client, db, acct, root = env
        _register(db, acct, root, "prospect_contacts.csv",
                  dataset="prospect_contacts")
        assert _listed(_manifest(client, acct))["filings"] == []

    def test_the_filings_list_csv_is_not_listed(self, env):
        client, db, acct, root = env
        _register(db, acct, root, "_filings_index.csv", body=b"company,url")
        assert _listed(_manifest(client, acct))["filings"] == []

    def test_an_account_with_no_filings_answers_with_an_empty_list(self, env):
        client, _db, acct, _root = env
        r = _manifest(client, acct)
        assert r.status_code == 200
        assert _listed(r)["filings"] == []

    def test_another_accounts_filings_are_not_listed(self, env):
        client, db, acct, root = env
        other = str(ObjectId())
        db["accounts"].insert_one({"_id": ObjectId(other), "name": "Other"})
        _register(db, other, root, AR)
        assert _listed(_manifest(client, acct))["filings"] == []

    def test_a_malformed_or_unknown_account_is_rejected(self, env):
        client, _db, _acct, _root = env
        assert _manifest(client, "not-an-object-id").status_code == 400
        assert _manifest(client, str(ObjectId())).status_code == 404


class TestTheTwoRoutesCannotDisagree:
    """Both go through `_viewable_filings`, so the manifest can never advertise a
    filing the document route would refuse, nor name a different one of two rows
    that share a filename. Asserted against each other rather than against a
    hardcoded expectation."""

    def test_everything_listed_can_actually_be_opened(self, env):
        client, db, acct, root = env
        _register(db, acct, root, AR)
        _register(db, acct, root, "second.pdf", body=b"%PDF-1.4 second")
        _register(db, acct, root, "gone.pdf", on_disk=False)
        _register(db, acct, root, "old.pdf", status="replaced")
        _register(db, acct, root, "_filings_index.csv", body=b"a,b")

        listed = [f["filename"] for f in _listed(_manifest(client, acct))["filings"]]
        assert listed == [AR, "second.pdf"]
        for name in listed:
            assert _get(client, acct, name).status_code == 200

    def test_nothing_openable_is_left_out_of_the_manifest(self, env):
        """The other direction: a filing the document route serves must be
        listed, or the UI would show plain text where a link was possible."""
        client, db, acct, root = env
        for name in (AR, "second.pdf", "third.pdf"):
            _register(db, acct, root, name)
        listed = {f["filename"] for f in _listed(_manifest(client, acct))["filings"]}
        for name in (AR, "second.pdf", "third.pdf"):
            assert _get(client, acct, name).status_code == 200
            assert name in listed

    def test_they_name_the_same_row_when_two_share_a_filename(self, env):
        client, db, acct, root = env
        for stored, body in (("zz_second.pdf", b"%PDF-1.4 second"),
                             ("aa_first.pdf", b"%PDF-1.4 first")):
            rel = "data/accounts/%s/compliance_filings/%s" % (acct, stored)
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            db["account_data_files"].insert_one({
                "account_id": acct, "dataset_key": "compliance_filings",
                "category": "compliance_filings", "original_filename": AR,
                "stored_filename": stored, "file_path": rel,
                "status": "active", "row_count": 9})

        listed = _listed(_manifest(client, acct))["filings"]
        assert [f["filename"] for f in listed] == [AR]
        assert _get(client, acct, AR).content == b"%PDF-1.4 first"


class TestTheManifestNeedsNoTokenInAUrl:

    def test_it_uses_the_ordinary_bearer_dependency(self, env):
        """Unlike the document route, this is fetched by the API client, so no
        JWT is put in a URL where it would reach browser history."""
        from app.api.v1 import account_data as mod
        route = next(r for r in mod.router.routes
                     if getattr(r, "path", "").endswith("/filings"))
        names = [d.call.__name__ for d in route.dependant.dependencies]
        assert "require_user_role" in names
        assert "require_user_role_flexible" not in names
        assert "get_current_user_flexible" not in names
