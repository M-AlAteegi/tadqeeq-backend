import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.history import get_regular_store
from app.core.rag import TadqeeqRAG, get_rag
from app.models.chat import QueryRequest, QueryResponse, Source

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _resolve_context(req: QueryRequest) -> list[dict] | None:
    if req.conversation_context is not None:
        return req.conversation_context
    if req.chat_id:
        return get_regular_store().conversation_context(req.chat_id)
    return None


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    rag = get_rag()
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG system is still initializing")
    store = get_regular_store()
    if req.chat_id:
        store.add_message(req.chat_id, "user", req.question)
    context = _resolve_context(req)
    result = await rag.generate_response(req.question, conversation_context=context)
    if req.chat_id:
        store.add_message(
            req.chat_id,
            "assistant",
            result["answer"],
            sources=result["sources"],
            regulator=result["regulator"],
        )
    return QueryResponse(
        answer=result["answer"],
        sources=[Source(**s) for s in result["sources"]],
        regulator=result["regulator"],
    )


async def _stream_events(
    rag: TadqeeqRAG, req: QueryRequest, request: Request
) -> AsyncIterator[str]:
    store = get_regular_store()
    if req.chat_id:
        store.add_message(req.chat_id, "user", req.question)
    context = _resolve_context(req)
    accumulated: list[str] = []
    last_sources: list[dict] = []
    last_regulator: str = "BOTH"
    aborted = False
    try:
        async for event in rag.stream_response(req.question, conversation_context=context):
            if await request.is_disconnected():
                aborted = True
                break
            if event["type"] == "meta":
                last_sources = event["sources"]
                last_regulator = event["regulator"]
            elif event["type"] == "token":
                accumulated.append(event["text"])
            yield _sse(event)
    finally:
        if req.chat_id and accumulated:
            text = "".join(accumulated).strip()
            if aborted:
                text += "\n\n_[stopped]_"
            store.add_message(
                req.chat_id, "assistant", text, sources=last_sources, regulator=last_regulator
            )


@router.post("/query/stream")
async def query_stream(req: QueryRequest, request: Request) -> StreamingResponse:
    rag = get_rag()
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG system is still initializing")
    return StreamingResponse(
        _stream_events(rag, req, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
