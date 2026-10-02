import os
from pathlib import Path

from pydantic_settings import BaseSettings

# Anchored to this file, not to the working directory.
#
# `env_file = ".env"` is resolved against the process CWD, so starting the
# backend from anywhere other than hp-backend/ found no .env at all. Every
# setting then fell back to its default - including MONGODB_URI, whose default
# is a local database. Writes went silently to the wrong place while the app
# looked healthy. Now that the team shares an Atlas cluster, that fallback
# would quietly split the data across two databases.
#
# settings.py lives at hp-backend/src/app/config/, so three levels up is the
# backend root and four is the repository root. The backend file is listed
# last: with a sequence, later files win.
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_CONFIG_DIR, "..", "..", ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_BACKEND_ROOT, ".."))

ENV_FILES = (
    os.path.join(_REPO_ROOT, ".env"),
    os.path.join(_BACKEND_ROOT, ".env"),
)


class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "hp_account_db"
    JWT_SECRET: str = "hp-account-intelligence-platform-secret-key-2026-enterprise"
    JWT_ALGORITHM: str = "HS256"
    # A working day. Two hours was shorter than a working session on this app -
    # one index build runs about 40 minutes - so sellers were being signed out
    # mid-task. Mirrored in both .env files; they are loaded as a sequence with
    # the backend one last, so a stale value there would silently override this.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    DATA_STORAGE_DIR: str = "data/accounts"

    # --- Which LLM provider every model call goes to -------------------------
    # "gemini" (Google AI Studio key, AIza...), "vertex" (Gemini on Vertex AI
    # with an express-mode API key, AQ....) or "openai" (the Azure OpenAI
    # deployment used until 28 Sep). Both are reached through the OpenAI SDK: Gemini exposes
    # an OpenAI-compatible endpoint, so chat, streaming, JSON mode and
    # embeddings keep one code path. Read the resolved values through the
    # properties at the bottom of this class, never the provider fields directly.
    LLM_PROVIDER: str = "gemini"

    GEMINI_API_KEY: str = ""
    GEMINI_ENDPOINT: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Every generated feature: plays, priorities, So What, signal scoring,
    # Content Studio, Strategy Chat answers. Flash: stable, fast, reliable JSON.
    GEMINI_MODEL_NAME: str = "gemini-2.5-flash"
    # LightRAG entity extraction and synthesis. Empty = GEMINI_MODEL_NAME.
    GEMINI_RETRIEVAL_MODEL: str = ""
    # gemini-embedding-001 returns 3072 dimensions. Changing the embedding model
    # or its dimension forces a full rebuild of every retrieval index
    # (ingest._update_index compares it with what built the index).
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBEDDING_DIM: int = 3072
    # Gemini 2.5's "thinking" tokens, per call. 0 turns it off: measured 28 Sep
    # on a news-scoring batch, 4.1 s and 685 tokens against 13.1 s and 1,673
    # with the model's default - and those tokens count against the rate limit
    # that was answering 429. Every prompt here spells out its rules and its
    # JSON shape, so it has little to reason about. -1 = the model's default.
    GEMINI_THINKING_BUDGET: int = 0
    # Vertex AI (LLM_PROVIDER=vertex). The express-mode key is GEMINI_API_KEY.
    # Chat goes to Vertex's OpenAI-compatible endpoint, which needs the project
    # and location in its path; embeddings go to the native predict method,
    # because that endpoint's embeddings route does not accept an API key.
    VERTEX_PROJECT: str = ""
    VERTEX_LOCATION: str = "global"
    # Embeddings go to a regional host: on the global one every request waited
    # ~12 s before its first byte (28 Sep, 1 or 16 texts alike), regional hosts
    # answer in under a second. asia-south1 is where the GCP VM runs.
    VERTEX_EMBEDDING_LOCATION: str = "asia-south1"

    # --- Azure OpenAI (LLM_PROVIDER=openai) ----------------------------------
    OPENAI_API_KEY: str = ""
    OPENAI_ENDPOINT: str = "https://accurix-foundry-resource.cognitiveservices.azure.com/openai/v1/"
    OPENAI_MODEL_NAME: str = "gpt-4o"
    # The retrieval layer is the only thing that embeds; OPENAI_API_KEY and
    # OPENAI_ENDPOINT above are reused as-is rather than duplicated for it.
    # 1536 is the output size of text-embedding-3-small - changing the model
    # means changing the dimension, and LightRAG refuses to reuse an index
    # built at a different one.
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIM: int = 1536
    # The model the retrieval layer uses for entity extraction and answer
    # synthesis. Left empty it falls back to OPENAI_MODEL_NAME, so the
    # retrieval layer can be moved to a different deployment without changing
    # what the other ten features run on.
    OPENAI_RETRIEVAL_MODEL: str = ""

    # Where the retrieval layer keeps its vectors.
    #   "atlas" - the three shared collections behind Atlas Vector Search
    #             (shared_vdb.py). Needs an Atlas cluster.
    #   "nano"  - LightRAG's NanoVectorDB: one set of files per workspace under
    #             RAG_STORAGE_DIR. Runs on any MongoDB, including a plain
    #             self-hosted one, which cannot serve $vectorSearch.
    # Defaults to "atlas" so a host that has not opted in keeps its vectors;
    # switching back is this one value, provided the Atlas data is still there.
    VECTOR_STORAGE: str = "atlas"
    # LightRAG's working directory, and with "nano" the only copy of every
    # vector - so it must sit on a persistent volume. Relative paths resolve
    # against hp-backend/, not the process working directory.
    RAG_STORAGE_DIR: str = "rag_storage"
    # Warm query handles kept open at once. Each "nano" handle holds its
    # workspace's vectors in memory (roughly 6 KB per vector), so an unbounded
    # cache grows with every account ever queried.
    QUERY_HANDLE_CACHE_SIZE: int = 20

    # --- Strategy Chat: the whole account in one call ------------------------
    # The chat reads every finished widget of the account at once (about
    # 113,000 tokens) instead of retrieving fragments of it, through the same
    # provider and client as everything else (core/gemini.py).
    #
    # Set explicitly because Gemini's default output cap is small. Too low
    # truncates the answer mid-sentence, which strips its trailing citation,
    # fails validation, and surfaces as a grounding error - a failure that
    # looks like anything except a token limit.
    # Measured, not guessed. Raised to 32,768 to stop a 90-day plan being
    # cut off; the model simply wrote 42,528 tokens instead, truncated
    # anyway, and spent 400 seconds doing it. The answer to an answer that
    # is too long is to ask for a shorter one - the prompt now does, and a
    # truncated attempt is retried shorter - not to widen the door.
    GEMINI_MAX_OUTPUT_TOKENS: int = 16384
    GEMINI_TEMPERATURE: float = 0.3

    # --- Observability -----------------------------------------------------
    # Stamped onto every log record, span and metric so that signals from the
    # backend stay distinguishable once other services share a project.
    SERVICE_NAME: str = "hp-backend"
    SERVICE_VERSION: str = "1.0.0"
    # Separates production telemetry from a laptop's in the same log store.
    ENVIRONMENT: str = "development"

    # DEBUG/INFO/WARNING/ERROR/CRITICAL. The level was hardcoded to INFO, so
    # turning on debug logging meant editing source; the debug calls already in
    # the extractors were effectively unreachable.
    LOG_LEVEL: str = "INFO"
    # "json" for one structured object per line - which is what Cloud Logging
    # parses into queryable fields - or "plain" for readable local output.
    # Defaults to json so that a deployed service is never accidentally
    # unstructured; set LOG_FORMAT=plain in a local .env.
    LOG_FORMAT: str = "json"

    # Empty disables the Google exporters. Tracing and metrics then fall back
    # to OTLP if an endpoint is set, and to nothing if not - the app still runs.
    GCP_PROJECT_ID: str = ""

    OTEL_ENABLED: bool = True
    # An OTLP collector, if one is used instead of or alongside Google's.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    # 1.0 samples every request. Fine at this traffic level and for a trace
    # store that bills per span; lower it before that stops being true.
    OTEL_TRACE_SAMPLE_RATIO: float = 1.0
    # Cloud Monitoring rejects a custom metric written more often than once a
    # minute, so exporting faster only wastes calls.
    OTEL_METRIC_EXPORT_INTERVAL_MS: int = 60000

    # --- The resolved LLM settings: the only place a caller should read -------
    @property
    def llm_provider(self) -> str:
        return (self.LLM_PROVIDER or "gemini").strip().lower()

    @property
    def _is_google(self) -> bool:
        return self.llm_provider in ("gemini", "vertex")

    @property
    def llm_api_key(self) -> str:
        key = self.GEMINI_API_KEY if self._is_google else self.OPENAI_API_KEY
        return (key or "").strip()

    @property
    def llm_api_key_name(self) -> str:
        """The env var a missing key is reported under."""
        return "GEMINI_API_KEY" if self._is_google else "OPENAI_API_KEY"

    @property
    def llm_endpoint(self) -> str:
        if self.llm_provider == "vertex":
            return ("https://aiplatform.googleapis.com/v1/projects/%s/locations/%s/"
                    "endpoints/openapi" % (self.VERTEX_PROJECT.strip(),
                                           (self.VERTEX_LOCATION or "global").strip()))
        ep = self.GEMINI_ENDPOINT if self.llm_provider == "gemini" else self.OPENAI_ENDPOINT
        return (ep or "").strip()

    @property
    def llm_client_kwargs(self) -> dict:
        """Arguments for openai.OpenAI(...). A Vertex express key travels in the
        x-goog-api-key header; sent as the Bearer token Vertex rejects it (401,
        wants OAuth). Not ?key=: a URL lands in error messages and logs."""
        if self.llm_provider == "vertex":
            return {"base_url": self.llm_endpoint, "api_key": "vertex-express",
                    "default_headers": {"x-goog-api-key": self.llm_api_key}}
        return {"base_url": self.llm_endpoint or None, "api_key": self.llm_api_key}

    @property
    def llm_request_extra(self) -> dict:
        """Extra arguments for every chat.completions.create call."""
        if not self._is_google or self.GEMINI_THINKING_BUDGET < 0:
            return {}
        # The OpenAI SDK's extra_body is merged into the request; Google reads
        # its own options from a body field that is itself named extra_body.
        return {"extra_body": {"extra_body": {"google": {"thinking_config": {
            "thinking_budget": int(self.GEMINI_THINKING_BUDGET)}}}}}

    def _google_model(self, name: str) -> str:
        # Vertex's OpenAI-compatible endpoint names Google's models google/<id>.
        name = name.strip()
        if self.llm_provider == "vertex" and "/" not in name:
            return "google/" + name
        return name

    @property
    def chat_model(self) -> str:
        if self._is_google:
            return self._google_model(self.GEMINI_MODEL_NAME or "gemini-2.5-flash")
        return (self.OPENAI_MODEL_NAME or "gpt-4o").strip()

    @property
    def retrieval_model(self) -> str:
        own = (self.GEMINI_RETRIEVAL_MODEL if self._is_google
               else self.OPENAI_RETRIEVAL_MODEL) or ""
        if not own.strip():
            return self.chat_model
        return self._google_model(own) if self._is_google else own.strip()

    @property
    def embedding_model(self) -> str:
        if self._is_google:
            return (self.GEMINI_EMBEDDING_MODEL or "gemini-embedding-001").strip()
        return (self.OPENAI_EMBEDDING_MODEL or "text-embedding-3-small").strip()

    @property
    def embedding_dim(self) -> int:
        return int(self.GEMINI_EMBEDDING_DIM if self._is_google
                   else self.OPENAI_EMBEDDING_DIM)

    @property
    def embedding_identity(self) -> str:
        """What built a vector: an index made by another identity is rebuilt."""
        return "%s:%s:%d" % (self.llm_provider, self.embedding_model, self.embedding_dim)

    class Config:
        env_file = ENV_FILES
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()


def backend_path(path: str) -> str:
    """`path` as an absolute path, relative ones anchored at hp-backend/."""
    return path if Path(path).is_absolute() else os.path.join(_BACKEND_ROOT, path)
