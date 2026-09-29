"""LightRAG must not cut an embedding request off during its own 429 waits.

Advantest's Executive Dashboard index failed twice on 29 Sep at document 12 of
14: the first eleven used up Vertex's per-minute embedding limit, the twelfth
got 429s, and `_vertex_post` waited 2 + 5 + 10 + 20 + 30 s to let the minute
pass. LightRAG killed the call at 60 s - its default 30 s timeout, doubled -
just before the attempt that would have landed, and one killed call fails the
whole build.

Run: python -m pytest tests/test_retrieval_embedding_timeout.py -v
"""

import inspect

from app.services.retrieval import client


def test_lightrags_cutoff_outlasts_every_wait_and_attempt():
    cutoff = 2 * client.EMBEDDING_TIMEOUT     # how LightRAG applies it
    attempts = len(client.VERTEX_RETRY_WAITS) + 1
    # Every wait, plus a generous 10 s for each attempt to answer.
    assert cutoff > sum(client.VERTEX_RETRY_WAITS) + 10 * attempts


def test_the_timeout_is_passed_to_lightrag():
    source = inspect.getsource(client.build_rag)
    assert "default_embedding_timeout=EMBEDDING_TIMEOUT" in source


def test_lightrag_still_doubles_the_timeout_into_its_cutoff():
    """If a LightRAG upgrade changes how the timeout becomes the cutoff, the
    arithmetic above stops being true - fail here rather than in a build."""
    from lightrag import lightrag as lr, utils

    assert "llm_timeout=self.default_embedding_timeout" in inspect.getsource(lr)
    assert "llm_timeout * 2" in inspect.getsource(utils.priority_limit_async_func_call)
