import os
import secrets
from functools import lru_cache
from typing import List, Literal, Optional, Union
from pydantic import EmailStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


INSECURE_SECRET_KEYS = {
    "",
    "change-this-in-production",
    "replace-with-a-long-random-secret",
    "secret",
    "secretkey",
    "admin",
    "password",
    "123456",
    "12345678",
    "test",
    "development",
}

INSECURE_ADMIN_PASSWORDS = {
    "",
    "change-me",
    "admin",
    "password",
    "123456",
    "12345678",
    "admin123",
    "root",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: Literal["development", "production", "test"] = "development"

    # Security & JWT
    SECRET_KEY: str = "dev-ephemeral-insecure-secret-key-for-local-testing-only-32bytes"
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "next-aura-voice-studio"
    JWT_AUDIENCE: str = "next-aura-clients"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Initial Admin Seed
    ADMIN_EMAIL: str = "admin@nextaura.io"
    ADMIN_PASSWORD: str = "change-me-dev-admin-pass-12345"
    ADMIN_MAX_LOGIN_ATTEMPTS: int = 5
    ADMIN_LOCKOUT_MINUTES: int = 15

    # Database
    DATABASE_URL: str = "sqlite:///./voice_clone.db"

    # Optional Redis for multi-instance distributed rate limiting / locking
    REDIS_URL: Optional[str] = None

    # VoxCPM Provider Configuration
    VOXCPM_PROVIDER: Literal["gradio", "mock", "self_hosted"] = "gradio"
    VOXCPM_SPACE: str = "openbmb/VoxCPM-Demo"
    HF_TOKEN: Optional[str] = None
    MAX_CONCURRENT_INFERENCES: int = 3
    INFERENCE_TIMEOUT_SECONDS: int = 90

    # Audio Upload Constraints
    MAX_AUDIO_BYTES: int = 12_000_000  # 12 MB
    MIN_AUDIO_DURATION_SECONDS: float = 0.5
    MAX_AUDIO_DURATION_SECONDS: float = 30.0

    # CORS & Cookies
    ALLOWED_ORIGINS: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    COOKIE_SECURE: Optional[bool] = None
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    ANONYMOUS_COOKIE_NAME: str = "na_anon_session"

    # Rate Limiting
    RATE_LIMIT_LOGIN_MAX: int = 5
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 60
    RATE_LIMIT_REGISTER_MAX: int = 3
    RATE_LIMIT_REGISTER_WINDOW_SECONDS: int = 60
    RATE_LIMIT_GENERATE_MAX: int = 5
    RATE_LIMIT_GENERATE_WINDOW_SECONDS: int = 60
    RATE_LIMIT_PURCHASE_MAX: int = 5
    RATE_LIMIT_PURCHASE_WINDOW_SECONDS: int = 60
    RATE_LIMIT_ADMIN_MAX: int = 30
    RATE_LIMIT_ADMIN_WINDOW_SECONDS: int = 60

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [orig.strip() for orig in v.split(",") if orig.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        is_prod = self.ENVIRONMENT == "production"

        # Resolve cookie security
        if self.COOKIE_SECURE is None:
            self.COOKIE_SECURE = is_prod

        if is_prod:
            # Check SECRET_KEY
            sec = self.SECRET_KEY.strip() if self.SECRET_KEY else ""
            if not sec or sec in INSECURE_SECRET_KEYS or len(sec) < 32:
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: SECRET_KEY must be set in production "
                    "to a strong random string of at least 32 characters. "
                    "Generate one using: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )

            # Check ADMIN_PASSWORD
            adm_pwd = self.ADMIN_PASSWORD.strip() if self.ADMIN_PASSWORD else ""
            if not adm_pwd or adm_pwd in INSECURE_ADMIN_PASSWORDS or len(adm_pwd) < 10:
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: ADMIN_PASSWORD must be explicitly configured "
                    "with a strong password (minimum 10 characters) in production."
                )

            # Check CORS
            if isinstance(self.ALLOWED_ORIGINS, list):
                if "*" in self.ALLOWED_ORIGINS:
                    raise ValueError(
                        "CRITICAL SECURITY CONFIGURATION ERROR: ALLOWED_ORIGINS cannot contain wildcard '*' "
                        "when credentials are enabled in production."
                    )
                if not self.ALLOWED_ORIGINS:
                    raise ValueError(
                        "CRITICAL SECURITY CONFIGURATION ERROR: ALLOWED_ORIGINS must contain at least one trusted origin in production."
                    )

        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
