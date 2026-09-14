"""The evidence registry - claim-level grounding that the model cannot forge.

Every checkable claim in the corpus gets a row here *before* any model sees it:

    { evidence_id, account_id, index, doc_id, dataset, record_id, field,
      source_text }

The document text carries each claim with its id inline, so the model can cite
one. But the model's citation is never the authority - it is a lookup key. When
a feature comes back with `evidence_ids`, Python resolves each one against this
registry, and an id that does not resolve, or resolves to a different account,
means the claim it supported is **dropped**.

That is the distinction between a citation and a citation-shaped string. The
same discipline the Message Evaluator already applies to phrase spans: a chunk
the model quotes that cannot be located in the draft is dropped and counted,
never re-anchored onto nearby text.
"""

import hashlib
import logging
import re

from app.database.mongodb import get_db

logger = logging.getLogger(__name__)

COLLECTION = "retrieval_evidence"

# doc_id#cN - the only shape a citation may take.
EVIDENCE_ID_RE = re.compile(r"^(?P<doc_id>[A-Za-z0-9_]+)#c(?P<n>\d+)$")


def evidence_id(doc_id: str, n: int) -> str:
    return "%s#c%d" % (doc_id, n)


def _text(value) -> str:
    return " ".join(str(value or "").split())


class EvidenceBuilder:
    """Accumulates the claims of one document, numbering them as it goes."""

    def __init__(self, account_id: str, index: str, doc_id: str, dataset: str):
        self.account_id = account_id
        self.index = index
        self.doc_id = doc_id
        self.dataset = dataset
        self.rows = []

    def add(self, source_text, field=None, record_id=None,
            publisher=None, source_url=None, dataset=None, quote=None) -> str | None:
        """Register one claim and return the id to write beside it in the text.

        `publisher` and `source_url` are carried when the evidence genuinely has
        them - a news row knows its outlet and its link - so a citation can read
        "IDNFinancials" with a working link instead of a dataset name. They are
        optional because most evidence has no external publisher, and inventing
        one would be worse than showing where it came from internally.

        `dataset` overrides the document's own dataset for a single row. A
        document often assembles material that originated elsewhere: an
        opportunity play restates a technographics cell, and without this the
        citation would name the document it was assembled in rather than the
        evidence behind the claim.

        `quote` is the raw value the derived sentence was built from - the cell
        actually read, like "AutoCAD" - so a reader can see the source, not only
        the sentence written about it.
        """
        text = _text(source_text)
        if not text:
            return None
        eid = evidence_id(self.doc_id, len(self.rows) + 1)
        row = {
            "evidence_id": eid,
            "account_id": self.account_id,
            "index": self.index,
            "doc_id": self.doc_id,
            "dataset": _text(dataset) or self.dataset,
            "record_id": None if record_id is None else str(record_id),
            "field": field,
            "source_text": text[:2000],
        }
        if _text(publisher):
            row["publisher"] = _text(publisher)
        if _text(source_url):
            row["source_url"] = _text(source_url)
        if _text(quote):
            row["quote"] = _text(quote)[:400]
        self.rows.append(row)
        return eid

    def line(self, source_text, field=None, record_id=None,
             publisher=None, source_url=None, dataset=None, quote=None) -> str:
        """A corpus line with its citation appended, or "" when there is nothing."""
        eid = self.add(source_text, field, record_id, publisher, source_url,
                       dataset, quote)
        return "" if not eid else "%s [%s]" % (_text(source_text), eid)


def replace_document_evidence(account_id: str, index: str, doc_id: str, rows: list):
    """Rewrite the registry for one document.

    Deleted first so a rebuilt document cannot leave behind ids that no longer
    appear anywhere in the corpus but would still resolve.
    """
    db = get_db()
    db[COLLECTION].delete_many(
        {"account_id": account_id, "index": index, "doc_id": doc_id})
    if rows:
        db[COLLECTION].insert_many([dict(r) for r in rows])


def resolve(account_id: str, index: str, ids) -> tuple:
    """(resolved, invalid). Account isolation is enforced by the query itself.

    An id belonging to another account simply does not resolve here - it is
    reported as invalid rather than returned, so a cross-account citation can
    never reach a seller.
    """
    wanted, invalid = [], []
    for raw in (ids or []):
        candidate = _text(raw)
        if EVIDENCE_ID_RE.match(candidate):
            wanted.append(candidate)
        else:
            invalid.append(candidate)

    if not wanted:
        return [], invalid

    db = get_db()
    found = list(db[COLLECTION].find(
        {"account_id": account_id, "index": index, "evidence_id": {"$in": wanted}},
        {"_id": 0}))
    by_id = {row["evidence_id"]: row for row in found}

    resolved = []
    for eid in wanted:
        row = by_id.get(eid)
        if row:
            resolved.append(row)
        else:
            invalid.append(eid)

    if invalid:
        logger.warning("retrieval: %d unresolvable evidence id(s) for account %s: %s",
                       len(invalid), account_id, invalid[:5])
    return resolved, invalid


def count(account_id: str, index: str) -> int:
    return get_db()[COLLECTION].count_documents(
        {"account_id": account_id, "index": index})


def purge(account_id: str, index: str):
    get_db()[COLLECTION].delete_many({"account_id": account_id, "index": index})


def fingerprint(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()
