from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine

logger = logging.getLogger(__name__)

# SQL keywords that indicate non-SELECT (write/DDL) operations
_DISALLOWED_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|EXEC|EXECUTE|MERGE|GRANT|REVOKE|DENY)\b",
    re.IGNORECASE,
)

# Bulk introspection query — single round-trip for all columns + PKs + FKs
_BULK_SCHEMA_SQL = """
SELECT
    t.TABLE_NAME,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE,
    CASE WHEN kcu.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_PK,
    fk_ref.REFERENCED_TABLE AS FK_TABLE,
    fk_ref.REFERENCED_COLUMN AS FK_COLUMN
FROM INFORMATION_SCHEMA.TABLES t
JOIN INFORMATION_SCHEMA.COLUMNS c
    ON c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME
LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON kcu.TABLE_SCHEMA = t.TABLE_SCHEMA
    AND kcu.TABLE_NAME = t.TABLE_NAME
    AND kcu.COLUMN_NAME = c.COLUMN_NAME
    AND kcu.CONSTRAINT_NAME IN (
        SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = t.TABLE_SCHEMA
          AND TABLE_NAME = t.TABLE_NAME
          AND CONSTRAINT_TYPE = 'PRIMARY KEY'
    )
LEFT JOIN (
    SELECT
        fkc.TABLE_SCHEMA, fkc.TABLE_NAME, fkc.COLUMN_NAME,
        pkc.TABLE_NAME AS REFERENCED_TABLE,
        pkc.COLUMN_NAME AS REFERENCED_COLUMN
    FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE fkc
        ON fkc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pkc
        ON pkc.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
        AND pkc.ORDINAL_POSITION = fkc.ORDINAL_POSITION
) fk_ref
    ON fk_ref.TABLE_SCHEMA = t.TABLE_SCHEMA
    AND fk_ref.TABLE_NAME = t.TABLE_NAME
    AND fk_ref.COLUMN_NAME = c.COLUMN_NAME
WHERE t.TABLE_SCHEMA = :schema
  AND t.TABLE_TYPE = 'BASE TABLE'
  AND t.TABLE_NAME IN (
    SELECT TOP (:max_tables) TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = :schema AND TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_NAME
  )
ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
"""


class SQLSafetyError(ValueError):
    """Raised when generated SQL contains disallowed statements."""


def validate_sql(sql: str) -> None:
    stripped = sql.strip()
    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        raise SQLSafetyError(
            "Only SELECT (and WITH…SELECT) statements are allowed. "
            f"Received: {stripped[:80]!r}"
        )
    if _DISALLOWED_PATTERN.search(stripped):
        match = _DISALLOWED_PATTERN.search(stripped)
        raise SQLSafetyError(
            f"Disallowed keyword '{match.group()}' found in generated SQL."
        )


def get_schema_info(max_tables: int = 200) -> dict[str, Any]:
    """
    Introspect the MSSQL database using a single bulk SQL query.
    Returns at most `max_tables` tables to keep embedding feasible.
    """
    settings = get_settings()
    engine = get_engine()

    schema_info: dict[str, Any] = {}

    with engine.connect() as conn:
        rows = conn.execute(
            text(_BULK_SCHEMA_SQL), {"schema": settings.mssql_schema, "max_tables": max_tables}
        ).fetchall()

    for row in rows:
        table_name = row[0]
        if table_name not in schema_info:
            if len(schema_info) >= max_tables:
                continue
            schema_info[table_name] = {"columns": [], "primary_keys": [], "foreign_keys": []}

        col = {
            "name": row[1],
            "type": row[2],
            "nullable": row[3] == "YES",
            "primary_key": bool(row[4]),
        }
        schema_info[table_name]["columns"].append(col)

        if col["primary_key"] and row[1] not in schema_info[table_name]["primary_keys"]:
            schema_info[table_name]["primary_keys"].append(row[1])

        if row[5]:  # FK reference exists
            fk = {"column": row[1], "references_table": row[5], "references_column": row[6]}
            if fk not in schema_info[table_name]["foreign_keys"]:
                schema_info[table_name]["foreign_keys"].append(fk)

    logger.info(
        "Introspected %d tables (max_tables=%d) from schema '%s'",
        len(schema_info), max_tables, settings.mssql_schema,
    )
    return schema_info


def schema_to_ddl_string(schema_info: dict[str, Any]) -> str:
    lines: list[str] = []
    for table, meta in schema_info.items():
        col_defs = []
        for col in meta["columns"]:
            pk_marker = " PRIMARY KEY" if col["primary_key"] else ""
            null_marker = "" if col["nullable"] else " NOT NULL"
            col_defs.append(f"  {col['name']} {col['type']}{pk_marker}{null_marker}")
        for fk in meta["foreign_keys"]:
            if fk["column"]:
                col_defs.append(
                    f"  FOREIGN KEY ({fk['column']}) REFERENCES {fk['references_table']}({fk['references_column']})"
                )
        lines.append(f"CREATE TABLE {table} (\n" + ",\n".join(col_defs) + "\n);")
    return "\n\n".join(lines)


def execute_query(sql: str) -> dict[str, Any]:
    """Execute a validated SELECT query and return column names + rows."""
    settings = get_settings()
    validate_sql(sql)

    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = result.fetchmany(settings.max_result_rows)

    return {
        "columns": [c if c else f"col_{i}" for i, c in enumerate(columns)],
        "rows": [dict(zip([c if c else f"col_{i}" for i, c in enumerate(columns)], row)) for row in rows],
        "row_count": len(rows),
    }
