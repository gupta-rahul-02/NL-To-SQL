from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.models import ChatRequest, ChatResponse, QueryResult
from app.services import memory_service, rag_service, llm_service, sql_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main NL-to-SQL endpoint.
    1. Load conversation history from Redis
    2. Retrieve relevant schema context from ChromaDB (RAG)
    3. Generate SQL via Ollama / LangChain
    4. Validate & execute SQL against MSSQL
    5. Generate plain-English explanation
    6. Persist the turn to Redis
    """
    session_id = request.session_id
    question = request.question

    # 1. Conversation history
    history = await memory_service.get_history(session_id)

    # 2. Schema context via RAG
    schema_context = rag_service.retrieve_schema_context(question)

    # 3. Generate SQL
    try:
        sql = llm_service.generate_sql(
            question=question,
            schema_context=schema_context,
            history=history,
        )
    except Exception as exc:
        logger.exception("LLM SQL generation failed")
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc

    # 3b. Guard: empty SQL means the model failed to generate anything
    if not sql:
        logger.warning("LLM returned empty SQL for question: %r", question)
        return ChatResponse(
            session_id=session_id,
            question=question,
            sql="",
            explanation="The model could not generate a SQL query. Try rephrasing the question or re-index the schema.",
            result=None,
            error="Model did not produce a SQL query. Please rephrase your question.",
        )

    # 4. Safety check + execute
    result_data: QueryResult | None = None
    exec_error: str | None = None
    try:
        sql_service.validate_sql(sql)
        raw = sql_service.execute_query(sql)
        result_data = QueryResult(**raw)
    except sql_service.SQLSafetyError as exc:
        exec_error = f"Safety check failed: {exc}"
        logger.warning("Safety check blocked query: %s", exc)
    except Exception as exc:
        exec_error = f"Query execution error: {exc}"
        logger.exception("Query execution failed: %s", sql)

    # 5. Explanation
    explanation = llm_service.explain_sql(sql=sql, question=question)

    # 6. Save turn (store explanation as assistant reply)
    assistant_reply = f"SQL: {sql}\n\nExplanation: {explanation}"
    if exec_error:
        assistant_reply += f"\n\nError: {exec_error}"
    await memory_service.append_turn(session_id, question, assistant_reply)

    return ChatResponse(
        session_id=session_id,
        question=question,
        sql=sql,
        explanation=explanation,
        result=result_data,
        error=exec_error,
    )


@router.delete("/chat/{session_id}")
async def clear_session(session_id: str) -> dict:
    """Clear conversation history for a session."""
    await memory_service.clear_history(session_id)
    return {"message": f"Session '{session_id}' cleared."}
