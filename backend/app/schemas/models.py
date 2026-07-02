from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1, max_length=128)


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class ChatResponse(BaseModel):
    session_id: str
    question: str
    sql: str
    explanation: str
    result: Optional[QueryResult] = None
    error: Optional[str] = None


# ── Schema indexing ───────────────────────────────────────────────────────────

class SchemaIndexResponse(BaseModel):
    tables_indexed: int
    docs_indexed: int
    message: str


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    database: bool
    redis: bool
    ollama: bool
