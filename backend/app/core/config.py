"""Application configuration and environment settings."""
import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Bakery Data Platform V4 - Sales Analytics API"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # MinIO / S3 Configuration
    S3_ENDPOINT: str = os.getenv("S3_ENDPOINT", os.getenv("MINIO_ENDPOINT", "minio:9000"))
    MINIO_ROOT_USER: str = os.getenv("MINIO_ROOT_USER", "bakeryadmin")
    MINIO_ROOT_PASSWORD: str = os.getenv("MINIO_ROOT_PASSWORD", "bakerydemo123")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() in ("true", "1")
    GOLD_BUCKET: str = os.getenv("GOLD_BUCKET", "bakery-gold")

    # DuckDB Extension Directory
    DUCKDB_EXT_DIR: str = os.getenv(
        "DUCKDB_EXT_DIR",
        str(Path(__file__).resolve().parents[3] / "state" / "duckdb_ext")
    )

    # CORS configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    class Config:
        case_sensitive = True


settings = Settings()
