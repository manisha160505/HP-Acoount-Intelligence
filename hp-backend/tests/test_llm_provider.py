"""The LLM provider switch (28 Sep): Gemini by default through its
OpenAI-compatible endpoint, Azure OpenAI with LLM_PROVIDER=openai.

Run: python -m pytest tests/test_llm_provider.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.config.settings import Settings
from app.core import llm


def _settings(**kw):
    base = {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "g-key", "OPENAI_API_KEY": "o-key",
            "GEMINI_RETRIEVAL_MODEL": "", "OPENAI_RETRIEVAL_MODEL": ""}
    base.update(kw)
    return Settings(_env_file=None, **base)


def test_gemini_is_the_default_and_resolves_everything():
    s = _settings()
    assert s.llm_provider == "gemini"
    assert s.llm_api_key == "g-key" and s.llm_api_key_name == "GEMINI_API_KEY"
    assert s.llm_endpoint.startswith("https://generativelanguage.googleapis.com/")
    assert s.chat_model == "gemini-2.5-flash"
    assert s.retrieval_model == "gemini-2.5-flash"          # falls back to chat
    assert s.embedding_identity == "gemini:gemini-embedding-001:3072"


def test_openai_is_one_setting_away():
    s = _settings(LLM_PROVIDER="openai")
    assert s.llm_api_key == "o-key" and s.chat_model == "gpt-4o"
    assert s.embedding_identity == "openai:text-embedding-3-small:1536"


def test_a_retrieval_model_override_moves_only_retrieval():
    s = _settings(GEMINI_RETRIEVAL_MODEL="gemini-2.5-pro")
    assert s.retrieval_model == "gemini-2.5-pro" and s.chat_model == "gemini-2.5-flash"


def test_a_fenced_json_answer_is_still_read():
    assert llm._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm._parse_json('```json {"a": 1}```') == {"a": 1}          # one line
    assert llm._parse_json('```{"a": 1}```') == {"a": 1}               # no tag
    assert llm._parse_json('{"a": 1}') == {"a": 1}
    assert llm._parse_json("") is None
    assert llm._parse_json("```json\n```") is None


def test_what_is_retried_and_what_is_not():
    import httpx
    import openai

    req = httpx.Request("POST", "http://x")

    def status(cls, code, msg="no"):
        return cls(msg, response=httpx.Response(code, request=req), body=None)

    retried = [status(openai.RateLimitError, 429), status(openai.InternalServerError, 503),
               openai.APITimeoutError(request=req), openai.APIConnectionError(request=req),
               httpx.ConnectError("reset"), httpx.ReadTimeout("slow"),
               status(openai.BadRequestError, 400, "maximum number of tokens allowed")]
    raised = [status(openai.BadRequestError, 400, "bad field"),
              status(openai.AuthenticationError, 401), status(openai.NotFoundError, 404),
              status(openai.UnprocessableEntityError, 422), RuntimeError("bug")]
    assert all(llm._retryable(e) and llm._moves_to_next_region(e) for e in retried)
    assert not any(llm._retryable(e) or llm._moves_to_next_region(e) for e in raised)


def test_vertex_sends_the_key_as_a_query_parameter_not_a_bearer_token():
    s = _settings(LLM_PROVIDER="vertex", VERTEX_PROJECT="123", VERTEX_LOCATION="global")
    kw = s.llm_client_kwargs
    assert kw["default_headers"] == {"x-goog-api-key": "g-key"} and kw["api_key"] != "g-key"
    assert "default_query" not in kw
    assert kw["base_url"] == ("https://aiplatform.googleapis.com/v1/projects/123/"
                              "locations/global/endpoints/openapi")


def test_vertex_names_google_models_with_their_publisher():
    s = _settings(LLM_PROVIDER="vertex", VERTEX_PROJECT="123")
    assert s.chat_model == "google/gemini-2.5-flash"
    assert s.retrieval_model == "google/gemini-2.5-flash"
    assert s.embedding_model == "gemini-embedding-001"      # native predict: no prefix
    assert s.embedding_identity == "vertex:gemini-embedding-001:3072"


def test_vertex_embeddings_send_key_in_header_and_wait_out_a_429(monkeypatch):
    import httpx

    from app.services.retrieval import client

    monkeypatch.setattr(client.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(client.settings, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(client, "VERTEX_RETRY_WAITS", (0, 0))
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        calls.append((url, headers, kw))
        code = 429 if len(calls) == 1 else 200
        body = {"predictions": [{"embeddings": {"values": [0.1]}}
                                for _ in json["instances"]]}
        return httpx.Response(code, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert client._vertex_embed(["a", "b"]) == [[0.1], [0.1]]
    assert len(calls) == 2
    url, headers, kw = calls[-1]
    assert headers == {"x-goog-api-key": "g-key"}
    assert "g-key" not in url and "params" not in kw


def test_regen_cancels_job_for_removed_node(monkeypatch):
    from app.services.regen import jobs
    from app.services.regen.engine import Engine

    finished = []

    def fake_finish(_db, _job, outcome, **_kw):
        finished.append(outcome)
        return True

    eng = Engine.__new__(Engine)
    eng.db = None
    eng.graph = {"news": object()}
    monkeypatch.setattr(jobs, "finish", fake_finish)
    out = eng.run_job({"account_id": "a1", "node_id": "messaging_context", "fence": 1})
    assert out["outcome"] == "cancelled" and finished == [jobs.CANCELLED]


def test_gemini_thinking_is_off_by_default_and_configurable():
    extra = _settings(LLM_PROVIDER="vertex", VERTEX_PROJECT="1").llm_request_extra
    assert extra["extra_body"]["extra_body"]["google"]["thinking_config"] == {"thinking_budget": 0}
    assert _settings(GEMINI_THINKING_BUDGET=-1).llm_request_extra == {}
    assert _settings(LLM_PROVIDER="openai").llm_request_extra == {}


def test_create_completion_waits_out_a_brief_429(monkeypatch):
    import httpx
    from openai import RateLimitError

    monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (0, 0))
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
    sent = []

    class _Completions:
        def create(self, **kw):
            sent.append(kw)
            if len(sent) < 3:
                raise RateLimitError("busy", response=httpx.Response(
                    429, request=httpx.Request("POST", "http://x")), body=None)
            return type("R", (), {"usage": None})()

    class _Client:
        chat = type("C", (), {"completions": _Completions()})()

    llm.create_completion(_Client(), model="m", messages=[])
    assert len(sent) == 3 and "extra_body" in sent[-1]


def test_a_429_that_outlasts_every_wait_flags_the_quota(monkeypatch):
    import time

    import httpx
    from openai import RateLimitError

    from app.services.regen import context as run_context

    monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (0, 0))

    class _Completions:
        def create(self, **_kw):
            raise RateLimitError("busy", response=httpx.Response(
                429, request=httpx.Request("POST", "http://x")), body=None)

    class _Client:
        chat = type("C", (), {"completions": _Completions()})()

    started = time.time()
    with pytest.raises(RateLimitError):
        llm.create_completion(_Client(), model="m", messages=[])
    assert run_context.quota_exhausted_since(started)


# ------------------------------------------- unreadable JSON is asked again

def _json_client(answers):
    """A client whose completions return `answers` in turn ("RAISE" raises)."""
    sent = []

    class _Completions:
        def create(self, **kw):
            sent.append(kw)
            answer = answers[len(sent) - 1]
            if answer == "RAISE":
                raise RuntimeError("connection reset")
            msg = type("M", (), {"content": answer})()
            return type("R", (), {"usage": None, "choices": [type("Ch", (), {"message": msg})()]})()

    class _Client:
        chat = type("C", (), {"completions": _Completions()})()

    return _Client(), sent


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(llm, "get_openai_client", lambda *_a, **_k: client)


def test_broken_json_is_asked_for_once_more(monkeypatch):
    client, sent = _json_client(['{"contacts": [{"id": "a" "x": 1}]}', '{"contacts": []}'])
    _patch_client(monkeypatch, client)
    assert llm.generate_gpt4o_json_completion("sys", "user") == {"contacts": []}
    assert len(sent) == 2


def test_an_empty_answer_is_asked_for_once_more(monkeypatch):
    client, sent = _json_client(["", '{"ok": true}'])
    _patch_client(monkeypatch, client)
    assert llm.generate_gpt4o_json_completion("sys", "user") == {"ok": True}
    assert len(sent) == 2


def test_two_unreadable_answers_fail_after_two_calls(monkeypatch):
    client, sent = _json_client(['{"a": 1,,}', '{"a" 1}'])
    _patch_client(monkeypatch, client)
    assert llm.generate_gpt4o_json_completion("sys", "user") is None
    assert len(sent) == 2


def test_a_readable_answer_is_not_asked_again(monkeypatch):
    client, sent = _json_client(['{"a": 1}', '{"a": 2}'])
    _patch_client(monkeypatch, client)
    assert llm.generate_gpt4o_json_completion("sys", "user") == {"a": 1}
    assert len(sent) == 1


def test_a_failed_call_is_not_retried_here(monkeypatch):
    client, sent = _json_client(["RAISE", '{"a": 1}'])
    _patch_client(monkeypatch, client)
    assert llm.generate_gpt4o_json_completion("sys", "user") is None
    assert len(sent) == 1


# --- the timeout cap (21 Oct) ------------------------------------------------
# A timeout costs the whole 300s request timeout. The region hops and the wait
# ladder used to repeat it up to ~24 x 5 times in one call; now at most
# MAX_TIMED_OUT_ATTEMPTS attempts may time out, each in a different region.

class _Regions:
    """A Vertex client: each per-region copy records its region on `log`."""

    def __init__(self, outcomes, log, base_url="https://x/locations/root/y"):
        self.outcomes, self.log, self.base_url = outcomes, log, base_url
        self.chat = self
        self.completions = self

    def with_options(self, base_url=None, max_retries=None):
        assert max_retries == 0
        return _Regions(self.outcomes, self.log, base_url)

    def create(self, **_kw):
        self.log.append(self.base_url.split("/locations/")[1].split("/")[0])
        item = self.outcomes(len(self.log))
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def _vertex(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "p")
    monkeypatch.setattr(llm.settings, "VERTEX_LOCATIONS", ",".join("r%d" % i
                                                                     for i in range(24)))
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    return sleeps


def _req():
    import httpx
    return httpx.Request("POST", "http://x")


def test_a_timeout_is_told_apart_from_a_fast_connection_failure():
    import httpx
    import openai

    assert llm._is_timeout(openai.APITimeoutError(request=_req()))
    assert llm._is_timeout(httpx.ReadTimeout("slow"))
    assert not llm._is_timeout(openai.APIConnectionError(request=_req()))
    assert not llm._is_timeout(httpx.ConnectError("reset"))
    assert llm.MAX_TIMED_OUT_ATTEMPTS == 3


def test_the_third_timeout_raises(_vertex):
    import openai

    log = []
    client = _Regions(lambda _n: openai.APITimeoutError(request=_req()), log)
    with pytest.raises(openai.APITimeoutError):
        llm.create_completion(client, affinity="a", model="m", messages=[])
    assert len(log) == 3 and len(set(log)) == 3      # three different regions
    assert _vertex == list(llm.RATE_LIMIT_WAITS[:2])  # backoff between them


def test_a_connection_reset_still_hops_to_the_next_region(_vertex):
    import openai

    log = []
    client = _Regions(lambda n: openai.APIConnectionError(request=_req()) if n < 4
                      else object(), log)
    llm.create_completion(client, affinity="a", model="m", messages=[])
    assert len(log) == 4 and len(set(log)) == 4 and _vertex == []


def test_timed_out_attempts_in_one_call_never_exceed_three(_vertex):
    import httpx
    import openai

    def status(cls, code):
        return cls(str(code), response=httpx.Response(code, request=_req()), body=None)

    log, kinds = [], []

    def outcome(n):
        # timeouts interleaved with resets, 429s and 5xx, for ever
        exc = [openai.APITimeoutError(request=_req()),
               openai.APIConnectionError(request=_req()),
               status(openai.RateLimitError, 429),
               status(openai.InternalServerError, 503)][n % 4]
        kinds.append(type(exc).__name__)
        return exc

    client = _Regions(outcome, log)
    with pytest.raises(openai.APIError):
        llm.create_completion(client, affinity="a", model="m", messages=[])
    assert kinds.count("APITimeoutError") == 3
    timed_regions = [r for r, k in zip(log, kinds) if k == "APITimeoutError"]
    assert len(set(timed_regions)) == 3
