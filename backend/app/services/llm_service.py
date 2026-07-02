from __future__ import annotations

import logging
import re
from typing import Any

from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────────

SQL_GENERATION_PROMPT = PromptTemplate(
    input_variables=["dialect", "schema_context", "conversation_history", "question"],
    template="""### Task
Generate a {dialect} SQL query to answer the question below.

### Rules
- Output ONLY the raw SQL statement. No explanations, no markdown, no code fences.
- Use SELECT only (no INSERT, UPDATE, DELETE, DROP, EXEC, etc.).
- Use {dialect} syntax: TOP N instead of LIMIT, square brackets for names with spaces.
- Start your answer directly with SELECT or WITH.
- CRITICAL: Use ONLY the exact table names and column names listed in the Database Schema section below. Do NOT invent, abbreviate, guess, or substitute table or column names. If the schema does not contain a relevant table, return: SELECT 'No relevant table found in schema' AS message

### Database Schema
{schema_context}

### Conversation History
{conversation_history}

### Question
{question}

### Answer
SELECT""",
)

EXPLANATION_PROMPT = PromptTemplate(
    input_variables=["sql", "question"],
    template="""Explain the following SQL query in simple, plain English (2-4 sentences).
Focus on WHAT the query retrieves and WHY it answers the user's question.
Do not mention SQL keywords unless essential for clarity.

Question: {question}
SQL: {sql}

Explanation:""",
)


# ── LLM instance (lazy) ───────────────────────────────────────────────────────

_llm: OllamaLLM | None = None


def _get_llm() -> OllamaLLM:
    global _llm
    if _llm is None:
        settings = get_settings()
        _llm = OllamaLLM(
            model=settings.ollama_sql_model,
            base_url=settings.ollama_base_url,
            temperature=0.0,       # deterministic SQL generation
            num_predict=1024,
            top_k=10,
        )
    return _llm


# ── Helper ────────────────────────────────────────────────────────────────────

def _clean_sql(raw: str) -> str:
    """Extract the SQL statement from LLM output, handling various output formats."""
    logger.debug("Raw LLM output: %r", raw[:500])
    raw = raw.strip()

    # Remove markdown code fences  ```sql ... ``` or ``` ... ```
    raw = re.sub(r"```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = raw.strip()

    # sqlcoder sometimes echoes the prompt marker — drop everything before the SQL
    for marker in ("### SQL QUERY ###", "### SQL ###", "SQL QUERY:", "SQL:", "### Answer"):
        idx = raw.upper().find(marker.upper())
        if idx != -1:
            raw = raw[idx + len(marker):].strip()

    # If the output doesn't start with SELECT/WITH, find the first occurrence
    if raw and not raw.upper().lstrip().startswith(("SELECT", "WITH")):
        match = re.search(r'(?:SELECT|WITH)\b', raw, re.IGNORECASE)
        if match:
            raw = raw[match.start():].strip()

    # Truncate at first blank line (model commentary after the SQL)
    first_blank = re.search(r'\n\s*\n', raw)
    if first_blank:
        raw = raw[:first_blank.start()].strip()

    return raw.strip()


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(no prior conversation)"
    parts = []
    for turn in history:
        role = "User" if turn["role"] == "user" else "Assistant"
        parts.append(f"{role}: {turn['content']}")
    return "\n".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_sql(
    question: str,
    schema_context: str,
    history: list[dict[str, str]],
) -> str:
    """
    Generate a SQL query for the given NL question using LangChain + Ollama.
    Returns the cleaned SQL string.
    """
    llm = _get_llm()
    chain = SQL_GENERATION_PROMPT | llm | StrOutputParser()

    raw_sql: str = chain.invoke(
        {
            "dialect": "MSSQL (Microsoft SQL Server)",
            "schema_context": schema_context or "(schema not available)",
            "conversation_history": _format_history(history),
            "question": question,
        }
    )
    logger.info("LLM raw output (%d chars): %r", len(raw_sql), raw_sql[:300])
    logger.info("Schema context length: %d chars", len(schema_context or ""))
    # The prompt ends with "SELECT" — prepend it back before cleaning
    raw_sql = "SELECT " + raw_sql
    cleaned = _clean_sql(raw_sql)
    if not cleaned:
        logger.warning("LLM produced no usable SQL. Raw output: %r", raw_sql[:500])
    return cleaned


def explain_sql(sql: str, question: str) -> str:
    """
    Generate a plain-English explanation of what the SQL query does.
    """
    llm = _get_llm()
    chain = EXPLANATION_PROMPT | llm | StrOutputParser()
    return chain.invoke({"sql": sql, "question": question}).strip()
