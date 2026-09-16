import os

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

    class Config:
        env_file = ENV_FILES
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
