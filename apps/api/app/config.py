from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True, env_ignore_empty=True
    )
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
    image_storage_root: Path = Path("/var/lib/assetvision/uploads")
    image_max_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=8 * 1024 * 1024)
    image_max_dimension: int = Field(default=8192, ge=64, le=16384)
    image_max_pixels: int = Field(default=16_000_000, ge=4096, le=24_000_000)
    recognition_encoder_name: Literal["mobilenet_v3_small", "shufflenet_v2_x0_5"] | None = None
    recognition_weights_root: Path = Path("/opt/weights/hub/checkpoints")
    ocr_models_root: Path | None = None
    image_max_per_model: int = Field(default=20, ge=5, le=100)

    @field_validator("image_storage_root", "recognition_weights_root", "ocr_models_root")
    @classmethod
    def absolute_storage_root(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("Storage/model root must be absolute")
        return value

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
