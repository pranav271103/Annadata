"""
Shared configuration for all Annadata OS services.
Reads from environment variables / .env file.
"""

import os
import warnings
from pathlib import Path
from typing import List, Optional, Union
from pydantic import model_validator, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SharedSettings(BaseSettings):
    """Base settings shared across all services."""

    # General
    APP_NAME: str = "Annadata"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "insecure-default-key-change-in-production"

    # Caching
    USE_SQLITE: bool = False  # Set to True for zero-install mode

    # PostgreSQL
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "annadata"
    POSTGRES_PASSWORD: str = "annadata_dev_password"
    POSTGRES_DB: str = "annadata"
    POSTGRES_PORT: str = "5432"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # AI
    NVIDIA_API_KEY: Optional[str] = None

    # JWT
    JWT_SECRET_KEY: str = "insecure-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def DATABASE_URL(self) -> str:
        if self.USE_SQLITE:
            return f"sqlite+aiosqlite:///{BASE_DIR / 'annadata.db'}"
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        if self.USE_SQLITE:
            return f"sqlite:///{BASE_DIR / 'annadata.db'}"
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.REDIS_URL

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URL

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        case_sensitive=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _check_production_secrets(self):
        """Prevent insecure default secrets from being used in production."""
        if self.APP_ENV.lower() == "production":
            if "insecure" in self.SECRET_KEY.lower():
                raise ValueError(
                    "SECRET_KEY contains 'insecure' — set a strong secret for production"
                )
            if "insecure" in self.JWT_SECRET_KEY.lower():
                raise ValueError(
                    "JWT_SECRET_KEY contains 'insecure' — set a strong secret for production"
                )
        return self


settings = SharedSettings()
