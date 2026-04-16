import os
from pathlib import Path
from typing import List, Union
from pydantic import AnyHttpUrl, validator
from services.shared.config import SharedSettings

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(SharedSettings):
    """
    Application settings configuration using Pydantic.
    Reads from environment variables and .env file.
    """

    # General App Settings
    APP_NAME: str = "Annadata"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # ACCESS_TOKEN_EXPIRE_MINUTES is already in SharedSettings

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # POSTGRES and REDIS are already in SharedSettings

    # SQLALCHEMY URLs are already in SharedSettings (DATABASE_URL/SYNC_DATABASE_URL)
    # Keeping properties for local backward compatibility
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return self.SYNC_DATABASE_URL

    @property
    def ASYNC_DATABASE_URI(self) -> str:
        return self.DATABASE_URL

    @property
    def REDIS_URL(self) -> str:
        return super().REDIS_URL

    # External APIs
    OPENWEATHER_API_KEY: str = ""
    SENTINEL_HUB_CLIENT_ID: str = ""
    SENTINEL_HUB_CLIENT_SECRET: str = ""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), case_sensitive=True, extra="ignore"
    )


settings = Settings()
