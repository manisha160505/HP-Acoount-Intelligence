"""Embedding calls spread over several Vertex regions (2 Oct): the embedding
limit is per region, and gemini-embedding-001 returns the same vectors in
every region, so rotating multiplies throughput without rebuilding an index.

Run: python -m pytest tests/test_embedding_regions.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.config.settings import Settings

REGIONS = "asia-south1, asia-southeast1,asia-northeast1"


def test_locations_default_to_the_single_region():
    s = Settings(_env_file=None, VERTEX_EMBEDDING_LOCATION="asia-south1",
                 VERTEX_EMBEDDING_LOCATIONS="")
    assert s.vertex_embedding_locations == ["asia-south1"]


def test_locations_list_is_parsed_in_order():
    s = Settings(_env_file=None, VERTEX_EMBEDDING_LOCATIONS=REGIONS + ",")
    assert s.vertex_embedding_locations == ["asia-south1", "asia-southeast1",
                                            "asia-northeast1"]


@pytest.fixture
def vertex(monkeypatch):
    import httpx

    from app.services.retrieval import client

    monkeypatch.setattr(client.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(client.settings, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(client.settings, "VERTEX_EMBEDDING_LOCATIONS", REGIONS)
    monkeypatch.setattr(client, "_location_turn", 0)
    monkeypatch.setattr(client, "VERTEX_RETRY_WAITS", (0,))
    calls = []

    def install(codes):
        """codes(url, n) -> status for the n-th call."""
        def fake_post(url, headers=None, json=None, timeout=None, **kw):
            calls.append(url)
            body = {"predictions": [{"embeddings": {"values": [0.3]}}
                                    for _ in json["instances"]]}
            return httpx.Response(codes(url, len(calls)), json=body,
                                  request=httpx.Request("POST", url))
        monkeypatch.setattr(httpx, "post", fake_post)
        return calls

    return client, install


def _region(url):
    return url.split("//")[1].split("-aiplatform")[0]


def test_successive_requests_rotate_regions(vertex):
    client, install = vertex
    calls = install(lambda _url, _n: 200)
    for _ in range(3):
        client._vertex_embed(["a"])
    assert [_region(u) for u in calls] == ["asia-south1", "asia-southeast1",
                                           "asia-northeast1"]


def test_a_429_moves_on_to_the_next_region_without_waiting(vertex, monkeypatch):
    client, install = vertex
    slept = []
    monkeypatch.setattr(client.time, "sleep", slept.append)
    calls = install(lambda url, _n: 429 if "asia-south1" in url else 200)
    assert client._vertex_embed(["a"]) == [[0.3]]
    assert [_region(u) for u in calls] == ["asia-south1", "asia-southeast1"]
    assert slept == []


def test_waits_only_when_every_region_refuses(vertex, monkeypatch):
    client, install = vertex
    slept = []
    monkeypatch.setattr(client.time, "sleep", slept.append)
    calls = install(lambda _url, n: 429 if n <= 3 else 200)
    assert client._vertex_embed(["a"]) == [[0.3]]
    assert len(calls) == 4 and slept == [0]


def test_every_region_refusing_after_all_waits_signals_quota(vertex, monkeypatch):
    import httpx

    from app.services.regen import context as run_context

    client, install = vertex
    noted = []
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)
    monkeypatch.setattr(run_context, "note_quota_exhausted", lambda: noted.append(1))
    install(lambda _url, _n: 429)
    with pytest.raises(httpx.HTTPStatusError):
        client._vertex_embed(["a"])
    assert noted == [1]
