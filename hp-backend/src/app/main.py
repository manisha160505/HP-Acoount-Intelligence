from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.database.mongodb import connect_to_mongo, close_mongo_connection
from app.database.seed import seed_users
from app.core.seeder import seed_database_if_empty
from app.api.v1.router import api_v1_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_to_mongo()
    seed_users()
    try:
        seed_database_if_empty()
    except Exception as e:
        print(f"[Startup Seeder Notice] {e}")
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
