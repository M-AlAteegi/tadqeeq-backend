from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    model = settings.claude_model if settings.llm_provider == "claude" else settings.ollama_model
    return {
        "status": "ok",
        "service": "tadqeeq-backend",
        "version": "0.1.0",
        "llm_provider": settings.llm_provider,
        "llm_model": model,
    }
