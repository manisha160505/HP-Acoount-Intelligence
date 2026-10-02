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
    assert llm._parse_json('{"a": 1}') == {"a": 1}
    assert llm._parse_json("") is None


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


def test_vertex_without_a_key_uses_adc_tokens_not_a_key_header():
    s = _settings(LLM_PROVIDER="vertex", GEMINI_API_KEY="", VERTEX_PROJECT="291820970173")
    assert s.vertex_keyless and s.llm_configured
    kw = s.llm_client_kwargs
    from app.core.google_auth import access_token
    assert kw["api_key"] is access_token                     # called per request
    assert "default_headers" not in kw
    assert "/projects/291820970173/" in kw["base_url"]


def test_vertex_keyless_needs_a_project_and_a_key_still_wins():
    assert not _settings(LLM_PROVIDER="vertex", GEMINI_API_KEY="",
                         VERTEX_PROJECT="").llm_configured
    with_key = _settings(LLM_PROVIDER="vertex", VERTEX_PROJECT="123")
    assert not with_key.vertex_keyless
    assert with_key.llm_client_kwargs["default_headers"] == {"x-goog-api-key": "g-key"}
    assert not _settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="",
                         VERTEX_PROJECT="123").llm_configured


def test_vertex_keyless_embeddings_name_the_project_and_send_a_bearer(monkeypatch):
    import httpx

    from app.core import google_auth
    from app.services.retrieval import client

    monkeypatch.setattr(client.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(client.settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(client.settings, "VERTEX_PROJECT", "291820970173")
    monkeypatch.setattr(client.settings, "VERTEX_EMBEDDING_LOCATION", "asia-south1")
    tokens = iter(["tok-1", "tok-2"])
    monkeypatch.setattr(google_auth, "access_token", lambda: next(tokens))
    monkeypatch.setattr(client, "VERTEX_RETRY_WAITS", (0,))
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        calls.append((url, headers))
        code = 429 if len(calls) == 1 else 200
        body = {"predictions": [{"embeddings": {"values": [0.2]}}
                                for _ in json["instances"]]}
        return httpx.Response(code, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert client._vertex_embed(["a"]) == [[0.2]]
    assert calls[0][0] == ("https://asia-south1-aiplatform.googleapis.com/v1/projects/"
                           "291820970173/locations/asia-south1/publishers/google/"
                           "models/gemini-embedding-001:predict")
    # a fresh token per attempt, so a long wait never resends an expired one
    assert [h for _, h in calls] == [{"Authorization": "Bearer tok-1"},
                                     {"Authorization": "Bearer tok-2"}]


def test_access_token_refreshes_only_when_invalid(monkeypatch):
    import google.auth

    from app.core import google_auth

    class _Creds:
        valid, token, refreshes = False, None, 0

        def refresh(self, _request):
            self.refreshes += 1
            self.valid, self.token = True, "t%d" % self.refreshes

    creds = _Creds()
    monkeypatch.setattr(google_auth, "_credentials", None)
    monkeypatch.setattr(google.auth, "default", lambda **_kw: (creds, "p"))
    assert google_auth.access_token() == "t1"
    assert google_auth.access_token() == "t1" and creds.refreshes == 1
    creds.valid = False                                      # expired
    assert google_auth.access_token() == "t2"


def test_missing_adc_is_a_clear_error(monkeypatch):
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    from app.core import google_auth

    def no_creds(**_kw):
        raise DefaultCredentialsError("none")

    monkeypatch.setattr(google_auth, "_credentials", None)
    monkeypatch.setattr(google.auth, "default", no_creds)
    with pytest.raises(google_auth.GoogleAuthError, match="application-default login"):
        google_auth.access_token()


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
