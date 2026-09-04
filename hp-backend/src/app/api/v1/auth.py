from fastapi import APIRouter, Depends
from app.schemas.user import UserLogin, TokenResponse, UserResponse
from app.schemas.auth import MessageResponse
from app.services.auth import authenticate_user
from app.core.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
def login(login_data: UserLogin):
    return authenticate_user(login_data)

@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

@router.post("/logout", response_model=MessageResponse)
def logout(current_user: dict = Depends(get_current_user)):
    return MessageResponse(message="Successfully logged out.")
