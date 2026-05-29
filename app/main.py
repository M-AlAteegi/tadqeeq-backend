import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, health, library
from app.config import settings
from app.core.library import get_library
from app.core.rag import get_rag
from app.providers import get_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting tadqeeq-backend (provider=%s)", settings.llm_provider)
    # Fail fast on misconfigured providers — raises if LLM_PROVIDER=claude but
    # CLAUDE_API_KEY is empty, instead of silently working until the first query.
    provider = get_provider()
    logger.info("Resolved LLM provider: %s", provider.name)
    get_library()  # eager-load clauses.json so first /library/index is instant
    await asyncio.to_thread(get_rag().initialize)
    logger.info("Startup complete")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="tadqeeq-backend",
    description="Bilingual (EN/AR) Islamic finance RAG service for Saudi (SAMA + CMA) compliance.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(library.router)
