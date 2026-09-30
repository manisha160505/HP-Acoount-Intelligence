import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from pymongo.errors import PyMongoError

from app.core.security import create_access_token, verify_password
from app.database.mongodb import get_db
from app.schemas.user import TokenResponse, UserLogin, UserResponse
from app.services.usage import record_login
from app.services.users_admin import is_user_active

logger = logging.getLogger(__name__)


def authenticate_user(login_data: UserLogin) -> TokenResponse:
    db = get_db()
    users_collection = db["users"]
    user = users_collection.find_one({"email": login_data.email.lower()})

    if not user or not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Checked after the password, so the message cannot be used to learn
    # which emails have accounts.
    if not is_user_active(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Contact your administrator.",
        )

    user_id = str(user["_id"])
    access_token = create_access_token(data={"sub": user_id, "role": user["role"]})

    # Bookkeeping only: neither write may fail the sign-in.
    try:
        users_collection.update_one({"_id": user["_id"]},
                                    {"$set": {"last_login_at": datetime.now(UTC)}})
    except PyMongoError:
        logger.exception("auth: could not record last_login_at")
    record_login(db, user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user_id,
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"]
        )
    )
