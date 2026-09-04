from fastapi import HTTPException, status
from app.database.mongodb import get_db
from app.core.security import verify_password, create_access_token
from app.schemas.user import UserLogin, TokenResponse, UserResponse

def authenticate_user(login_data: UserLogin) -> TokenResponse:
    db = get_db()
    users_collection = db["users"]
    user = users_collection.find_one({"email": login_data.email.lower()})
    
    if not user or not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    user_id = str(user["_id"])
    access_token = create_access_token(data={"sub": user_id, "role": user["role"]})
    
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
