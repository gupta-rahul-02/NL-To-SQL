from __future__ import annotations

import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, schema, health as health_route
from app.core.config import get_settings
from app.services import memory_service


def setup_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield
    # Graceful shutdown
    await memory_service.close()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NL-to-SQL AI",
        description="Natural Language to SQL query system powered by local LLMs.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — allow the Next.js frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health_route.router, tags=["Health"])
    app.include_router(chat.router, prefix="/api", tags=["Chat"])
    app.include_router(schema.router, prefix="/api", tags=["Schema"])

    return app


app = create_app()
