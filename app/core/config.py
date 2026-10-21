"""Application configuration (Pydantic Settings)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # HTTP Basic credentials for document endpoints
    API_KEY: str | None = Field(default=None)
    API_SECRET: str | None = Field(default=None)

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://docuser:docpass@localhost:5432/docservice"
    )

    # Redis (ARQ)
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Storage
    STORAGE_BACKEND: str = Field(default="local")
    STORAGE_ROOT: str = Field(default="/app/data/storage")
    STORAGE_BUCKET: str | None = Field(default=None)
    MAX_FILE_SIZE_BYTES: int = Field(default=104857600)

    # OCR
    OCR_LANGUAGE: str = Field(default="eng")
    MAX_OCR_PAGES: int = Field(default=50, ge=1)
    MAX_OCR_BATCH_FILES: int = Field(default=20, ge=1)
    MAX_MCP_FILE_SIZE_BYTES: int = Field(default=8388608, ge=1024)
    MCP_ALLOWED_HOSTS: str = Field(default="localhost:*,127.0.0.1:*")
    MCP_ALLOWED_ORIGINS: str = Field(default="http://localhost:*,http://127.0.0.1:*")

    # PDF optimization (pikepdf/qpdf)
    ENABLE_PDF_OPTIMIZE: bool = Field(default=True)

    # Compression
    DEFAULT_COMPRESSION_LEVEL: int = Field(default=6)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
