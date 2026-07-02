from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.mssql_connection_string,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=(settings.app_env == "development"),
    )


def check_db_connection() -> bool:
    """Lightweight connectivity check used by /health endpoint."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
