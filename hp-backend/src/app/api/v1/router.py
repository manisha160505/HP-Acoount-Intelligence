from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.accounts import router as accounts_router
from app.api.v1.account_data import router as account_data_router
from app.api.v1.account_config import router as account_config_router
from app.api.v1.feature_mapping import router as feature_mapping_router
from app.api.v1.widgets import router as widgets_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(accounts_router)
api_v1_router.include_router(account_data_router)
api_v1_router.include_router(account_config_router)
api_v1_router.include_router(feature_mapping_router)
api_v1_router.include_router(widgets_router)
