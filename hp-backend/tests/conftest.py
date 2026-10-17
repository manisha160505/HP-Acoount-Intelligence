"""A throwaway signing key for the whole test run: the app has no default."""

from app.config.settings import settings
from app.core.security import generate_private_key_pem

settings.JWT_PRIVATE_KEY = generate_private_key_pem()
