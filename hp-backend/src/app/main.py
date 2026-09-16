import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.config.settings import settings
from app.core.seeder import seed_database_if_empty
from app.database.mongodb import close_mongo_connection, connect_to_mongo, get_db
from app.database.seed import seed_users
from app.errors import register_error_handlers
from app.observability import setup_observability, shutdown_observability
from app.observability.envelope_middleware import ResponseEnvelopeMiddleware
from app.observability.middleware import RequestLoggingMiddleware
from app.observability.tracing import instrument_app

# Called before anything else so that every log line from the imports below,
# the seeder and the retrieval worker goes through the configured formatter.
# Previously a bare basicConfig here emitted unstructured text: readable at a
# terminal, unqueryable in a log store, and with nothing tying a line to the
# request that produced it.
setup_observability()
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

    # Started only after seeding has finished, so it cannot pick up a job that
    # seeding would otherwise have queued. Seeding itself runs with retrieval
    # triggers suppressed, so there should be none - this ordering is the
    # second guard rather than the first.
    try:
        from app.services.retrieval import worker as retrieval_worker
        retrieval_worker.start()
    except Exception:
        logger.exception("Retrieval worker did not start. Indexes will not "
                         "rebuild until it does; widgets are unaffected.")

    _log_readiness()
    yield

    try:
        from app.services.retrieval import worker as retrieval_worker
        retrieval_worker.stop()
    except Exception:
        logger.exception("Retrieval worker did not stop cleanly.")
    close_mongo_connection()
    # Last: both exporters buffer, so the telemetry for the final requests
    # before a redeploy is only kept if they are flushed explicitly.
    shutdown_observability()


app = FastAPI(
    title="HP Account Intelligence API",
    description="Enterprise Account Intelligence Platform Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Registered first, so it runs INNERMOST - closest to the route. It has to see
# the handler's own JSON body before anything else touches it, and it must not
# see the error bodies the exception handlers produce (those are already
# enveloped, and it skips 4xx/5xx for that reason).
app.add_middleware(ResponseEnvelopeMiddleware)

# Starlette runs middleware in reverse order of registration, so this must be
# added before CORS for CORS to be the outermost layer - otherwise a request
# rejected by CORS would never reach the logger, and an exception raised inside
# it would return a 500 without the CORS headers the browser needs to read it.
app.add_middleware(RequestLoggingMiddleware)

# CORS Middleware Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The frontend reads this off a failed response to show the id a user can
    # quote in a bug report. A cross-origin caller cannot see a header that is
    # not explicitly exposed, so without this it reads as undefined.
    expose_headers=["X-Request-ID"],
)

# After the middleware stack is assembled: the instrumentor wraps the app as it
# stands when called.
instrument_app(app)

# Every failure path - a raised APIError, a plain HTTPException, a schema
# validation failure, or an uncaught exception - is normalised into one JSON
# body here, with the request id attached so a user-reported failure has
# something to search the logs on. `detail` stays a plain string inside that
# body, so the frontend sites that render it directly keep working unchanged.
register_error_handlers(app)

app.include_router(api_v1_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "HP Account Intelligence Platform API"}
