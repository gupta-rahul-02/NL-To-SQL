from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# ── Redis (optional) ─────────────────────────────────────────────────────────
_redis_available = False
_redis_pool: Any = None

try:
    import redis.asyncio as aioredis  # type: ignore
    _redis_available = True
except ImportError:
    pass

# ── In-memory fallback ────────────────────────────────────────────────────────
_in_memory_store: dict[str, list[str]] = defaultdict(list)


def _get_settings():
    from app.core.config import get_settings
    return get_settings()


async def _get_redis():
    global _redis_pool, _redis_available
    if not _redis_available:
        return None
    if _redis_pool is None:
        settings = _get_settings()
        try:
            pool = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await pool.ping()
            _redis_pool = pool
            logger.info("Connected to Redis at %s", settings.redis_url)
        except Exception as exc:
            logger.warning("Redis unavailable (%s) — using in-memory conversation store", exc)
            _redis_available = False
            _redis_pool = None
            return None
    return _redis_pool


def _session_key(session_id: str) -> str:
    return f"nl2sql:session:{session_id}"


async def get_history(session_id: str) -> list[dict[str, str]]:
    """
    Return the conversation history for a session as a list of
    {"role": "user"|"assistant", "content": "..."} dicts.
    """
    settings = _get_settings()
    r = await _get_redis()
    key = _session_key(session_id)

    if r:
        raw: list[str] = await r.lrange(key, 0, -1)
        await r.expire(key, settings.conversation_ttl_seconds)
    else:
        raw = list(_in_memory_store[key])

    history: list[dict[str, str]] = []
    for item in raw:
        role, _, content = item.partition("|")
        history.append({"role": role, "content": content})
    return history


async def append_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """Append a user/assistant turn to the session history."""
    settings = _get_settings()
    r = await _get_redis()
    key = _session_key(session_id)

    if r:
        await r.rpush(key, f"user|{user_message}", f"assistant|{assistant_message}")
        await r.expire(key, settings.conversation_ttl_seconds)
    else:
        _in_memory_store[key].extend([f"user|{user_message}", f"assistant|{assistant_message}"])


async def clear_history(session_id: str) -> None:
    """Delete all history for a session."""
    r = await _get_redis()
    key = _session_key(session_id)
    if r:
        await r.delete(key)
    else:
        _in_memory_store.pop(key, None)


async def close() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
