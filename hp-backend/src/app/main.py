import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.database.mongodb import connect_to_mongo, close_mongo_connection, get_db
from app.database.seed import seed_users
from app.core.seeder import seed_database_if_empty
from app.api.v1.router import api_v1_router

# Nothing configured the root logger, so every logger.info in the extractors and
# the seeder was discarded and only warnings reached stderr. The startup summary
# below is worthless without this.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# The placeholder shipped in .env.example. It is a non-empty string, so it
# passes a truthiness check and fails only at the API call - worth naming.
PLACEHOLDER_KEY = "your-azure-openai-api-key-here"


def _log_readiness() -> None:
    """State what the app actually came up with, so a blank UI is diagnosable."""
    try:
        db = get_db()
        account = db["accounts"].find_one({}, {"_id": 1, "name": 1})
        if account:
            datasets = db["account_data_files"].count_documents(
                {"account_id": str(account["_id"]), "status": "active"})
            widgets = db["account_widgets"].count_documents(
                {"account_id": str(account["_id"])})
            logger.info("Ready: account %s (%s) with %d active dataset(s), %d widget(s).",
                        account["_id"], account.get("name", "?"), datasets, widgets)
        else:
            logger.warning("Ready, but no account exists. Every feature will render empty.")
    except Exception:
        logger.exception("Could not summarise startup state.")

    key = (settings.OPENAI_API_KEY or "").strip()
    if not key:
        logger.warning("OPENAI_API_KEY is not set - AI-inferred layers will stay "
                       "empty by design. Deterministic widgets are unaffected.")
    elif key == PLACEHOLDER_KEY:
        logger.warning("OPENAI_API_KEY is still the .env.example placeholder - "
                       "AI generation will fail at the API call.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Raises if the database is unreachable. Serving an app whose every query
    # will time out is worse than refusing to start: the old code caught this,
    # printed a notice, and left the UI blank with no working explanation.
    connect_to_mongo()

    seed_users()
    try:
        seed_database_if_empty()
    except Exception:
        logger.exception("Seeding failed. Features that depend on seeded data "
                         "will render empty.")

    _log_readiness()
    yield
    close_mongo_connection()


app = FastAPI(
    title="HP Account Intelligence API",
    description="Enterprise Account Intelligence Platform Backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "HP Account Intelligence Platform API"}
