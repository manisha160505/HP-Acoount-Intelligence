from pymongo import MongoClient
from app.config.settings import settings

class MongoDB:
    client: MongoClient = None
    db = None

db_instance = MongoDB()

def connect_to_mongo():
    db_instance.client = MongoClient(settings.MONGODB_URI)
    db_instance.db = db_instance.client[settings.DB_NAME]
    print(f"Connected to MongoDB at {settings.MONGODB_URI}, Database: {settings.DB_NAME}")

def close_mongo_connection():
    if db_instance.client:
        db_instance.client.close()
        print("MongoDB connection closed.")

def get_db():
    if db_instance.db is None:
        connect_to_mongo()
    return db_instance.db
