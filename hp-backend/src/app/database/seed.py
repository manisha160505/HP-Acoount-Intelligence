from datetime import datetime, timezone
from app.database.mongodb import get_db
from app.core.security import get_password_hash

def seed_users():
    db = get_db()
    users_collection = db["users"]

    # Check and seed Admin
    admin_user = users_collection.find_one({"email": "admin@hp.com"})
    if not admin_user:
        users_collection.insert_one({
            "email": "admin@hp.com",
            "password_hash": get_password_hash("AdminPassword123!"),
            "full_name": "HP System Administrator",
            "role": "admin",
            "created_at": datetime.now(timezone.utc)
        })
        print("Seeded default Admin user: admin@hp.com")

    # Check and seed User
    sales_user = users_collection.find_one({"email": "user@hp.com"})
    if not sales_user:
        users_collection.insert_one({
            "email": "user@hp.com",
            "password_hash": get_password_hash("UserPassword123!"),
            "full_name": "HP Enterprise Sales Representative",
            "role": "user",
            "created_at": datetime.now(timezone.utc)
        })
        print("Seeded default Sales user: user@hp.com")
