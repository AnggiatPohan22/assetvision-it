from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "production"] = "development"
    postgres_db: str = "assetvision"
    postgres_user: str = "assetvision"
    postgres_password: SecretStr = SecretStr("")
    postgres_host: str = "db"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    database_url: SecretStr | None = None
    jwt_secret: SecretStr
    access_token_expire_minutes: int = Field(default=15, ge=1, le=30)
    cookie_secure: bool = False
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("jwt_secret")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or secret.lower().startswith("change"):
            raise ValueError("JWT_SECRET must contain at least 32 random characters")
        return value

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if not self.database_url and not self.postgres_password.get_secret_value():
            raise ValueError("POSTGRES_PASSWORD or DATABASE_URL is required")
        if self.app_env == "production" and not self.cookie_secure:
            raise ValueError("Production requires COOKIE_SECURE=true and HTTPS")
        if not self.origins or any(
            not origin.startswith(("http://", "https://")) or origin.endswith("/")
            for origin in self.origins
        ):
            raise ValueError("ALLOWED_ORIGINS requires exact origins without trailing slashes")
        return self

    @property
    def origins(self) -> set[str]:
        return {origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()}

    @property
    def db_url(self) -> str | URL:
        if self.database_url:
            url = make_url(self.database_url.get_secret_value())
            if url.get_backend_name() == "postgresql":
                return url.update_query_dict({"options": "-csearch_path=public"})
            return url
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
            query={"options": "-csearch_path=public"},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
