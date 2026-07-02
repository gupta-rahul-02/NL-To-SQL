from __future__ import annotations

import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.core.db import check_db_connection
from app.schemas.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()

    # Database
    db_ok = check_db_connection()

    # Redis
    redis_ok = False
    try:
        from app.services.memory_service import _get_redis
        r = await _get_redis()
        if r:
            redis_ok = await r.ping()
    except Exception:
        pass

    # Ollama
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    overall = "ok" if all([db_ok, redis_ok, ollama_ok]) else "degraded"
    return HealthResponse(
        status=overall,
        database=db_ok,
        redis=redis_ok,
        ollama=ollama_ok,
    )
