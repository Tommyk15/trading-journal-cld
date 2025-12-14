"""Application configuration using Pydantic settings."""

from functools import lru_cache

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Trading Journal"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="trading_journal")
    postgres_password: str = Field(default="trading_journal")
    postgres_db: str = Field(default="trading_journal")
    database_url: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None, values) -> str:
        """Build database URL from components if not provided."""
        if isinstance(v, str):
            return v

        data = values.data if hasattr(values, 'data') else {}
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=data.get("postgres_user", "trading_journal"),
            password=data.get("postgres_password", "trading_journal"),
            host=data.get("postgres_host", "localhost"),
            port=data.get("postgres_port", 5432),
            path=data.get("postgres_db", "trading_journal"),
        ).unicode_string()

    # IBKR Configuration
    ibkr_host: str = Field(default="127.0.0.1")
    ibkr_port: int = Field(default=7496)
    ibkr_client_id: int = Field(default=1)

    # IBKR Flex Query Configuration
    ibkr_flex_token: str | None = Field(default=None)
    ibkr_flex_query_id: str = Field(default="1348073")

    # API Settings
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )

    # Polygon.io Configuration
    polygon_api_key: str | None = Field(default=None)

    # FRED API Configuration
    fred_api_key: str | None = Field(default=None)


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
