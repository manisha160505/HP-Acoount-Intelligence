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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    DATA_STORAGE_DIR: str = "data/accounts"
    
    OPENAI_API_KEY: str = ""
    OPENAI_ENDPOINT: str = "https://accurix-foundry-resource.cognitiveservices.azure.com/openai/v1/"
    OPENAI_MODEL_NAME: str = "gpt-4o"

    class Config:
        env_file = ENV_FILES
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
