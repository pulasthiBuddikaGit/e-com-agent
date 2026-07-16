from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Kapruka AI Shopping Agent"
    environment: str = "development"
    api_prefix: str = "/api"

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    kapruka_mcp_url: str = Field(
        default="https://mcp.kapruka.com/mcp",
        alias="KAPRUKA_MCP_URL",
    )
    mcp_connect_timeout_seconds: float = Field(default=8.0, alias="MCP_CONNECT_TIMEOUT_SECONDS")
    mcp_read_timeout_seconds: float = Field(default=20.0, alias="MCP_READ_TIMEOUT_SECONDS")
    mcp_total_timeout_seconds: float = Field(default=30.0, alias="MCP_TOTAL_TIMEOUT_SECONDS")

    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    product_cache_ttl_seconds: int = Field(default=1800, alias="PRODUCT_CACHE_TTL_SECONDS")
    category_cache_ttl_seconds: int = Field(default=1800, alias="CATEGORY_CACHE_TTL_SECONDS")

    mcp_requests_per_minute: int = Field(default=60, alias="MCP_REQUESTS_PER_MINUTE")
    create_order_requests_per_hour: int = Field(
        default=30,
        alias="CREATE_ORDER_REQUESTS_PER_HOUR",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

