"""Querying an index, normalised into our own contract.

Nothing outside this module should know what LightRAG's response looks like.
`aquery` returns a string in some configurations and a dict in others depending
on `include_references` and `only_need_context`, and that shape has changed
across releases - so it is mapped here into `RetrievalResult` once, and the
features depend on that.

There is one workspace per (account, index), so a build writes into the same
place queries read. That "place" is now two things: this account's own KV, graph
and doc-status collections, and its partition of the three shared vector
collections - which every account shares, separated by an Atlas pre-filter on
the workspace name. A query therefore cannot see another account's vectors, and
the graph it walks is this account's alone.

What a build means for a query:

  * an **incremental update** touches only the documents that changed, so a
    query during one still answers from everything else;
  * a **full rebuild** drops the workspace first, so there is genuinely nothing
    to read. A query during one is refused with that as the reason, rather than
    returning an empty answer that looks like "no such fact".
"""

import logging
import re

from app.services.retrieval import client, index_state, registry

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 40
EVIDENCE_ID_RE = re.compile(r"[A-Za-z0-9_]+#c\d+")


class IndexNotReady(Exception):
    """There is nothing to query yet, and the reason is worth showing."""


class RetrievalResult:
    """What a feature gets back. Stable regardless of the library's shape."""

    def __init__(self, answer="", context="", document_ids=None, file_paths=None,
                 evidence_ids=None, mode="", workspace="", stale=False):
        self.answer = answer or ""
        self.context = context or ""
        self.document_ids = list(document_ids or [])
        self.file_paths = list(file_paths or [])
        self.evidence_ids = list(evidence_ids or [])
        self.mode = mode
        self.workspace = workspace
        self.stale = stale

    def as_dict(self) -> dict:
        return {
            "answer": self.answer,
            "document_ids": self.document_ids,
            "file_paths": self.file_paths,
            "evidence_ids": self.evidence_ids,
            "mode": self.mode,
            "workspace": self.workspace,
            "stale": self.stale,
        }


def _normalise(raw, mode, workspace, stale) -> RetrievalResult:
    """Map whatever came back into the contract.

    `include_references` yields a dict on 1.5.7; plain string responses and
    `only_need_context` output are handled too, so a library change degrades to
    a usable answer rather than an exception.
    """
    answer, context, file_paths, doc_ids = "", "", [], []

    if isinstance(raw, dict):
        # aquery_llm nests the generated text under llm_response.
        llm = raw.get("llm_response") or {}
        answer = (llm.get("content") if isinstance(llm, dict) else None) \
            or raw.get("response") or raw.get("answer") or ""

        data = raw.get("data") or raw.get("retrieval") or {}
        context = raw.get("context") or raw.get("retrieved_context") or ""
        if not context and isinstance(data, dict):
            context = data.get("context") or ""

        refs = raw.get("references") or []
        if not refs and isinstance(data, dict):
            refs = data.get("references") or []
        if not refs and isinstance(llm, dict):
            refs = llm.get("references") or []

        # Chunks carry their own file_path even when no reference list is
        # emitted, so they are the fallback source of attribution - and their
        # text is where the inline evidence ids live.
        chunks = []
        for holder in (raw, data):
            if isinstance(holder, dict):
                chunks.extend(holder.get("chunks") or [])
        parts = [context]
        for chunk in chunks:
            if isinstance(chunk, dict):
                path = chunk.get("file_path")
                if path and path not in file_paths:
                    file_paths.append(str(path))
                parts.append(str(chunk.get("content") or chunk.get("text") or ""))
        context = "\n".join(p for p in parts if p)

        for ref in refs:
            if isinstance(ref, dict):
                path = ref.get("file_path") or ref.get("source") or ref.get("path")
                doc = ref.get("doc_id") or ref.get("id")
                if path and path not in file_paths:
                    file_paths.append(str(path))
                if doc and doc not in doc_ids:
                    doc_ids.append(str(doc))
            elif ref and str(ref) not in file_paths:
                file_paths.append(str(ref))
    else:
        answer = str(raw or "")

    blob = "%s\n%s" % (answer, context)
    evidence_ids = list(dict.fromkeys(EVIDENCE_ID_RE.findall(blob)))

    return RetrievalResult(answer=answer, context=context, document_ids=doc_ids,
                           file_paths=file_paths, evidence_ids=evidence_ids,
                           mode=mode, workspace=workspace, stale=stale)


async def retrieve(account_id: str, index: str, question: str, mode: str | None = None,
                   top_k: int = DEFAULT_TOP_K, only_context: bool = False,
                   conversation_history=None) -> RetrievalResult:
    """Ask one index one question."""
    from lightrag import QueryParam

    state = index_state.get(account_id, index)
    workspace = state.get("workspace")

    # Refused rather than attempted. Opening a retired workspace would answer
    # from an empty graph, which reads as "no such fact" instead of "no index".
    if state.get("status") == index_state.RETIRED:
        raise IndexNotReady(
            "this index was retired, so it cannot answer. The feature still "
            "shows its last published output.")

    if not workspace or state.get("status") == index_state.BUILDING:
        raise IndexNotReady(
            "a full rebuild is in progress - this index is unavailable until it "
            "finishes" if state.get("status") == index_state.BUILDING
            else (state.get("last_error")
                  or "no index has been built for this account yet"))

    mode = mode or registry.spec(index).get("default_mode") or "mix"
    stale = state.get("status") in (index_state.STALE, index_state.FAILED)

    rag = await client.build_rag(account_id, index)
    try:
        param = QueryParam(
            mode=mode,
            top_k=top_k,
            only_need_context=only_context,
            include_references=True,
            # Defaults to True, but no rerank model is configured - LightRAG
            # then warns on every query and reranks nothing. Off until a model
            # is actually wired, rather than leaving a no-op path enabled.
            enable_rerank=False,
            conversation_history=list(conversation_history or []),
        )
        # aquery() is a backward-compatibility wrapper that returns only the
        # response string and throws the references away. aquery_llm() is the
        # real entry point and returns the structured result, which is where
        # include_references actually lands.
        raw = await rag.aquery_llm(question, param=param)
    finally:
        try:
            await rag.finalize_storages()
        except Exception:
            logger.exception("retrieval: finalize_storages failed after query")

    result = _normalise(raw, mode, workspace, stale)
    logger.info("retrieval: %s/%s answered in %s mode (%d refs, %d evidence ids)",
                account_id, index, mode, len(result.file_paths),
                len(result.evidence_ids))
    return result


def status(account_id: str, index: str) -> dict:
    """What the UI and the admin endpoint show."""
    state = index_state.get(account_id, index)
    entry = registry.spec(index)
    return {
        "index": index,
        "label": entry.get("label"),
        "enabled": bool(entry.get("enabled")),
        "status": state.get("status"),
        "version": state.get("version"),
        "workspace": state.get("workspace"),
        "last_build_mode": state.get("last_build_mode"),
        "damaged_documents": state.get("damaged_documents") or [],
        "documents": len(state.get("documents") or {}),
        "last_built_at": state.get("last_built_at"),
        "last_error": state.get("last_error"),
        # Reported separately from the index's own status: the index built fine,
        # the thing downstream of it did not.
        "generation_error": state.get("generation_error"),
        "build_count": state.get("build_count"),
        "notice": entry.get("notice"),
    }
