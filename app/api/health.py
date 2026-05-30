from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.core.rag import get_rag

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    """Public health endpoint — also surfaces corpus stats so the web
    welcome screen can populate without a separate authenticated call."""
    model = settings.claude_model if settings.llm_provider == "claude" else settings.ollama_model
    rag = get_rag()
    stats = {"sama": 0, "cma": 0, "total": 0}
    if rag.ready and rag.stats:
        sama = rag.stats.get("SAMA", {})
        cma = rag.stats.get("CMA", {})
        stats["sama"] = sama.get("en", 0) + sama.get("ar", 0)
        stats["cma"] = cma.get("en", 0) + cma.get("ar", 0)
        stats["total"] = stats["sama"] + stats["cma"]
    return {
        "status": "ok",
        "service": "tadqeeq-backend",
        "version": "0.1.0",
        "llm_provider": settings.llm_provider,
        "llm_model": model,
        "stats": stats,
    }
