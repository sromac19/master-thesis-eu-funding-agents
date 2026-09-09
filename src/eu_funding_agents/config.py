from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://eu_funding:eu_funding@localhost:5432/eu_funding"
    database_health_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    checkpoint_database_url: str = ""
    llm_provider: str = "openai"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_temperature: float = Field(default=0.0, ge=0, le=2)
    llm_max_tokens: int = Field(default=2000, ge=1, le=32000)
    llm_max_input_chars: int = Field(default=120000, ge=1000, le=500000)
    reranker_model_path: Path | None = None
    cordis_api_key: str = ""
    call_refresh_hours: int = Field(default=24, ge=1, le=720)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
