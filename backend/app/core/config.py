from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── MSSQL ──────────────────────────────────────────────────────────────────
    mssql_server: str = "localhost"
    mssql_port: int = 1433
    mssql_database: str
    mssql_username: str
    mssql_password: str
    mssql_driver: str = "ODBC+Driver+17+for+SQL+Server"
    mssql_schema: str = "dbo"

    # ── Ollama ─────────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://ollama:11434"
    ollama_sql_model: str = "defog/sqlcoder-7b-2"
    ollama_embed_model: str = "nomic-embed-text"

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379"
    conversation_ttl_seconds: int = 86400

    # ── ChromaDB / Vector Store ────────────────────────────────────────────────
    chroma_persist_path: str = "./chroma_data"
    chroma_collection_name: str = "schema_docs"  # kept for compat

    # ── App ────────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    max_result_rows: int = 500
    max_schema_tables: int = 200  # cap for indexing (2530-table DBs need this)

    @property
    def mssql_connection_string(self) -> str:
        return (
            f"mssql+pyodbc://{self.mssql_username}:{self.mssql_password}"
            f"@{self.mssql_server}:{self.mssql_port}/{self.mssql_database}"
            f"?driver={self.mssql_driver}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
