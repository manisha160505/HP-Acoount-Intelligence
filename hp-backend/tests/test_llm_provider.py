"""The LLM provider switch (28 Sep): Gemini by default through its
OpenAI-compatible endpoint, Azure OpenAI with LLM_PROVIDER=openai.

Run: python -m pytest tests/test_llm_provider.py -v
"""

import os
import sys

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
    assert kw["default_query"] == {"key": "g-key"} and kw["api_key"] != "g-key"
    assert kw["base_url"] == ("https://aiplatform.googleapis.com/v1/projects/123/"
                              "locations/global/endpoints/openapi")


def test_vertex_names_google_models_with_their_publisher():
    s = _settings(LLM_PROVIDER="vertex", VERTEX_PROJECT="123")
    assert s.chat_model == "google/gemini-2.5-flash"
    assert s.retrieval_model == "google/gemini-2.5-flash"
    assert s.embedding_model == "gemini-embedding-001"      # native predict: no prefix
    assert s.embedding_identity == "vertex:gemini-embedding-001:3072"
