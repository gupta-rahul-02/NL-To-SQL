from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.models import SchemaIndexResponse
from app.services import rag_service, sql_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/schema/index", response_model=SchemaIndexResponse)
def index_schema() -> SchemaIndexResponse:
    """
    Introspect MSSQL schema + index schema_docs markdown files into ChromaDB.
    Call this once on startup (or after schema changes).
    """
    settings = get_settings()
    schema_info = sql_service.get_schema_info(max_tables=settings.max_schema_tables)
    try:
        tables_indexed = rag_service.index_schema(schema_info)
    except Exception as exc:
        logger.exception("Schema indexing failed mid-way: %s", exc)
        # Return partial results — whatever was saved before the failure
        partial = sum(1 for k in rag_service._store if k.startswith("table::"))
        return SchemaIndexResponse(
            tables_indexed=partial,
            docs_indexed=0,
            message=f"Partial index: {partial} tables saved before error: {exc}",
        )
    docs_indexed = rag_service.index_schema_docs()

    return SchemaIndexResponse(
        tables_indexed=tables_indexed,
        docs_indexed=docs_indexed,
        message=f"Indexed {tables_indexed} tables and {docs_indexed} doc files.",
    )


@router.get("/schema/tables")
def list_tables() -> dict:
    """Return a list of tables and their column info (without executing queries)."""
    schema_info = sql_service.get_schema_info()
    return {"tables": list(schema_info.keys()), "schema": schema_info}
