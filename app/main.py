import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import (
    analysis,
    chat,
    chats,
    exports,
    health,
    library,
    library_chats,
)
from app.api import (
    settings as settings_router,
)
from app.config import settings
from app.core.auth import BearerAuthMiddleware
from app.core.library import get_library
from app.core.limits import limiter
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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(BearerAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(chats.router)
app.include_router(library.router)
app.include_router(library_chats.router)
app.include_router(analysis.router)
app.include_router(exports.router)
app.include_router(settings_router.router)
