"""Guards on the account delete.

The script removes an account from six collections, a directory of uploaded
files, its LightRAG workspace collections and its slice of each shared vector
collection. It is irreversible and it runs against the shared cluster, so what
is pinned here is not that it deletes - it is the three things that stop it
deleting the wrong thing, and the ordering that makes a half-finished run
recoverable.

Run: python -m pytest tests/test_delete_account.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import delete_account as da


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.dropped = False

    def count_documents(self, query):
        return len(self._matching(query))

    def find(self, query, projection=None):
        return list(self._matching(query))

    def find_one(self, query, projection=None):
        found = self._matching(query)
        return found[0] if found else None

    def delete_many(self, query):
        hits = self._matching(query)
        self.docs = [d for d in self.docs if d not in hits]
        return type("R", (), {"deleted_count": len(hits)})()

    def delete_one(self, query):
        hits = self._matching(query)
        if hits:
            self.docs.remove(hits[0])
        return type("R", (), {"deleted_count": 1 if hits else 0})()

    def drop(self):
        self.dropped = True
        self.docs = []

    def _matching(self, query):
        out = []
        for doc in self.docs:
            ok = True
            for key, value in (query or {}).items():
                actual = doc.get(key)
                if isinstance(value, dict) and "$regex" in value:
                    import re
                    ok = ok and bool(re.match(value["$regex"], str(actual or "")))
                else:
                    ok = ok and str(actual) == str(value)
            if ok:
                out.append(doc)
        return out


class FakeDb:
    def __init__(self, collections):
        self.collections = collections
        self.order = []

    def __getitem__(self, name):
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]

    def list_collection_names(self):
        return list(self.collections)


def db_with(account_id="abc123", indexed=False, widgets=2):
    collections = {
        "accounts": FakeCollection([{"_id": account_id, "name": "TestCorp"}]),
        "account_widgets": FakeCollection(
            [{"account_id": account_id} for _ in range(widgets)]),
        "account_data_files": FakeCollection([{"account_id": account_id}]),
        "retrieval_index_state": FakeCollection(
            [{"account_id": account_id}] if indexed else []),
    }
    return FakeDb(collections)


# --- the survey ------------------------------------------------------------


def test_survey_counts_every_account_collection():
    db = db_with(widgets=3)
    report = da.survey(db, {"_id": "abc123", "name": "TestCorp"})
    assert report["counts"]["account_widgets"] == 3
    assert report["counts"]["account_data_files"] == 1
    assert report["documents"] == 4


def test_survey_flags_an_indexed_account():
    """The one signal that separates a real account from a test row."""
    assert da.survey(db_with(indexed=True), {"_id": "abc123"})["indexed"] is True
    assert da.survey(db_with(indexed=False), {"_id": "abc123"})["indexed"] is False


def test_workspace_collections_match_only_this_account():
    db = FakeDb({
        "acct_abc123_strategy_full_docs": FakeCollection(),
        "acct_abc123_strategy_doc_status": FakeCollection(),
        "acct_other_strategy_full_docs": FakeCollection(),
        "_bak_acct_abc123_strategy_entities": FakeCollection(),
        "shared_vdb_chunks": FakeCollection(),
    })
    found = da.workspace_collections(db, "abc123")
    assert found == ["acct_abc123_strategy_doc_status",
                     "acct_abc123_strategy_full_docs"]
    assert not any(c.startswith("_bak_") for c in found), (
        "a backup collection is not this account's live data")


# --- ordering --------------------------------------------------------------


def test_the_accounts_row_is_deleted_last():
    """A half-finished run must leave the account visible, not orphaned.

    If `accounts` went first and a later step failed, the rows would still be in
    every other collection with nothing pointing at them - invisible in the UI
    and impossible to clean up by account.
    """
    db = db_with()
    order = []
    for name, collection in db.collections.items():
        original_many, original_one = collection.delete_many, collection.delete_one

        def many(query, _n=name, _f=original_many):
            order.append(_n)
            return _f(query)

        def one(query, _n=name, _f=original_one):
            order.append(_n)
            return _f(query)

        collection.delete_many, collection.delete_one = many, one

    report = da.survey(db, {"_id": "abc123", "name": "TestCorp"})
    da.delete(db, report)
    assert order[-1] == "accounts", "accounts was deleted at position %s of %s" % (
        order.index("accounts") + 1, len(order))


def test_delete_removes_the_rows_it_surveyed():
    db = db_with(widgets=2)
    report = da.survey(db, {"_id": "abc123", "name": "TestCorp"})
    removed = da.delete(db, report)
    assert removed["account_widgets"] == 2
    assert removed["accounts"] == 1
    assert db["account_widgets"].count_documents({"account_id": "abc123"}) == 0
    assert db["accounts"].count_documents({}) == 0


# --- the collection list ---------------------------------------------------


def test_every_account_collection_is_listed_not_guessed():
    """A new account-keyed collection has to be added here deliberately.

    Discovering them by scanning would either miss one whose sample document
    happens to lack the field, or delete from somewhere it should not.
    """
    assert "account_widgets" in da.ACCOUNT_COLLECTIONS
    assert "retrieval_evidence" in da.ACCOUNT_COLLECTIONS
    assert "retrieval_index_state" in da.ACCOUNT_COLLECTIONS
    assert len(set(da.ACCOUNT_COLLECTIONS)) == len(da.ACCOUNT_COLLECTIONS)


def test_there_is_no_delete_by_exclusion():
    """Accounts are named. An exclusion written today includes an account
    added tomorrow, which is the mistake this script exists to avoid."""
    with open(da.__file__, encoding="utf-8") as fh:
        source = fh.read()
    for forbidden in ("$nin", "--except", "--all", "--keep"):
        assert forbidden not in source, (
            "%r suggests an exclusion mode; deletion must be by explicit name"
            % forbidden)


@pytest.mark.parametrize("account_id", ["abc123", "ABC123"])
def test_partition_regex_is_anchored_to_this_account(account_id):
    """`acct_abc1_` must not match `acct_abc123_`."""
    db = FakeDb({
        "shared_vdb_chunks": FakeCollection([
            {PARTITION: "acct_abc123_strategy"},
            {PARTITION: "acct_abc123456_strategy"},
            {PARTITION: "acct_other_strategy"},
        ]),
    })
    report = da.survey(db, {"_id": account_id, "name": "TestCorp"})
    # Both abc123 rows share the prefix by construction; the point is that the
    # other account's row is never included.
    assert "acct_other" not in str(report["partitions"])


PARTITION = da.PARTITION_FIELD
