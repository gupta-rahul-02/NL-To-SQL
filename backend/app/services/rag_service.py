from __future__ import annotations

"""
Pure-Python RAG service using Ollama embeddings + numpy cosine similarity.
No C++ compiler required — replaces ChromaDB dependency.
Embeddings are persisted to a JSON file for reuse across restarts.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── In-memory store: {doc_id: {"text": str, "embedding": list[float]}} ───────
_store: dict[str, dict] = {}
_store_path: Path | None = None


def _get_store_path() -> Path:
    global _store_path
    if _store_path is None:
        settings = get_settings()
        p = Path(settings.chroma_persist_path)
        p.mkdir(parents=True, exist_ok=True)
        _store_path = p / "vector_store.json"
    return _store_path


def _load_store() -> None:
    """Load persisted embeddings from disk if available."""
    path = _get_store_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _store.update(data)
            logger.info("Loaded %d vectors from %s", len(_store), path)
        except Exception as exc:
            logger.warning("Could not load vector store: %s", exc)


def _save_store() -> None:
    path = _get_store_path()
    path.write_text(json.dumps(_store), encoding="utf-8")


def _embed(texts: list[str]) -> list[list[float]]:
    """Call Ollama embedding API for a list of texts. Retries once on 500, then skips."""
    settings = get_settings()
    embeddings: list[list[float] | None] = []
    with httpx.Client(timeout=60.0) as client:
        for text in texts:
            # Truncate to ~2000 chars to avoid context overflow in embedding model
            truncated = text[:2000]
            emb = None
            for attempt in range(3):  # up to 3 attempts per text
                try:
                    resp = client.post(
                        f"{settings.ollama_base_url}/api/embeddings",
                        json={"model": settings.ollama_embed_model, "prompt": truncated},
                    )
                    resp.raise_for_status()
                    emb = resp.json()["embedding"]
                    break
                except Exception as exc:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        "Embedding attempt %d/3 failed (len=%d): %s — retrying in %ds",
                        attempt + 1, len(truncated), exc, wait,
                    )
                    time.sleep(wait)
            if emb is None:
                logger.error("Skipping embedding after 3 failures for text starting: %r", truncated[:80])
            embeddings.append(emb)
    return embeddings


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ── Public API ────────────────────────────────────────────────────────────────

def index_schema(schema_info: dict[str, Any]) -> int:
    """Embed and store each table's schema info. Saves in batches of 50 for resilience."""
    if not _store:
        _load_store()

    documents: list[tuple[str, str]] = []  # (doc_id, text)
    for table_name, meta in schema_info.items():
        col_lines = [
            f"  - {col['name']} ({col['type']})"
            + (" [PK]" if col["primary_key"] else "")
            + ("" if col["nullable"] else " NOT NULL")
            for col in meta["columns"]
        ]
        fk_lines = [
            f"  - {fk['column']} → {fk['references_table']}.{fk['references_column']}"
            for fk in meta["foreign_keys"]
            if fk["column"]
        ]
        text = f"Table: {table_name}\nColumns:\n" + "\n".join(col_lines)
        if fk_lines:
            text += "\nForeign Keys:\n" + "\n".join(fk_lines)
        documents.append((f"table::{table_name}", text))

    indexed = 0
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        embeddings = _embed([t for _, t in batch])
        for (doc_id, text), emb in zip(batch, embeddings):
            if emb is not None:
                _store[doc_id] = {"text": text, "embedding": emb}
                indexed += 1
        _save_store()  # persist after every batch so progress isn't lost
        logger.info("Indexed batch %d-%d (%d/%d done)", i, i + len(batch), indexed, len(documents))

    logger.info("Indexed %d/%d tables total", indexed, len(documents))
    return indexed


def index_schema_docs(schema_docs_path: str = "./schema_docs") -> int:
    """Embed and store markdown files from schema_docs/ directory."""
    if not _store:
        _load_store()

    docs_dir = Path(schema_docs_path)
    if not docs_dir.exists():
        logger.warning("schema_docs path does not exist: %s", schema_docs_path)
        return 0

    documents: list[tuple[str, str]] = []
    for file_path in docs_dir.glob("**/*.md"):
        content = file_path.read_text(encoding="utf-8")
        documents.append((f"doc::{file_path.stem}", content))

    if documents:
        embeddings = _embed([t for _, t in documents])
        for (doc_id, text), emb in zip(documents, embeddings):
            _store[doc_id] = {"text": text, "embedding": emb}
        _save_store()
        logger.info("Indexed %d schema doc files", len(documents))

    return len(documents)


def retrieve_schema_context(query: str, n_results: int = 8) -> str:
    """Retrieve most relevant schema chunks for the NL query via cosine similarity."""
    if not _store:
        _load_store()
    if not _store:
        return ""

    try:
        query_emb = np.array(_embed([query])[0])
    except Exception as exc:
        logger.warning("Embedding query failed: %s — returning all schema", exc)
        chunks = [v["text"] for v in list(_store.values())[:n_results]]
        return "\n\n---\n\n".join(chunks)

    scored = [
        (doc_id, _cosine_similarity(query_emb, np.array(v["embedding"])), v["text"])
        for doc_id, v in _store.items()
    ]

    # Boost table entries based on name matches in the query (case-insensitive)
    query_upper = query.upper()
    # Split query into words for prefix matching
    query_words = set(query_upper.split())
    boosted = []
    for doc_id, score, text in scored:
        if doc_id.startswith("table::"):
            table_name = doc_id[len("table::"):].upper()
            # Strong boost: exact table name appears verbatim in query
            if table_name in query_upper:
                score = min(1.0, score + 0.3)
            # Weaker boost: table name prefix (>=3 chars) appears inside any query word
            # e.g. table "INVC" prefix "INV" found inside query word "INVOICE"
            elif len(table_name) >= 3:
                prefix = table_name[:3]
                if any(prefix in word for word in query_words):
                    score = min(1.0, score + 0.15)
        boosted.append((doc_id, score, text))

    boosted.sort(key=lambda x: x[1], reverse=True)
    top = boosted[:n_results]
    return "\n\n---\n\n".join(text for _, _, text in top)
