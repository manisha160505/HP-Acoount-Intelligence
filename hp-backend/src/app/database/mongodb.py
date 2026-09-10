import logging
import re

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config.settings import settings

logger = logging.getLogger(__name__)

# How long to wait for a server before giving up. pymongo's default is 30s,
# which turned an unreachable database into a half-minute hang on every single
# request instead of an obvious failure at startup.
SERVER_SELECTION_TIMEOUT_MS = 5000

# mongodb+srv://user:password@cluster.../db -> hide the password when logging.
_CREDENTIALS_RE = re.compile(r"://([^:/@]+):([^@]+)@")


def redact_uri(uri: str) -> str:
    """A connection string safe to put in a log line."""
    return _CREDENTIALS_RE.sub(r"://\1:***@", str(uri or ""))


class MongoDB:
    client: MongoClient = None
    db = None


db_instance = MongoDB()


def connect_to_mongo():
    """Open a connection and prove it works before reporting success.

    MongoClient() is lazy - it opens no socket and raises nothing, so the old
    unconditional "Connected to MongoDB" print was emitted even when no server
    existed. The first real query then failed 30 seconds later, by which point
    the log had already said the database was fine. Everything downstream
    (seeding, extraction, every widget) silently produced nothing.
    """
    safe_uri = redact_uri(settings.MONGODB_URI)
    client = MongoClient(settings.MONGODB_URI,
                         serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS)
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        client.close()
        logger.error(
            "Cannot reach MongoDB at %s (%s). The database must be running and "
            "reachable, and for Atlas this machine's IP must be allowlisted. "
            "Nothing can be seeded or extracted until it is.",
            safe_uri, type(exc).__name__,
        )
        raise

    db_instance.client = client
    db_instance.db = client[settings.DB_NAME]
    logger.info("Connected to MongoDB at %s, database: %s", safe_uri, settings.DB_NAME)
    return db_instance.db


def close_mongo_connection():
    if db_instance.client:
        db_instance.client.close()
        db_instance.client = None
        db_instance.db = None
        logger.info("MongoDB connection closed.")


def get_db():
    if db_instance.db is None:
        connect_to_mongo()
    return db_instance.db
