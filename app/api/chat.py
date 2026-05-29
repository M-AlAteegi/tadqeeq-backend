import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.rag import TadqeeqRAG, get_rag
from app.models.chat import QueryRequest, QueryResponse, Source

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _stream_events(
    rag: TadqeeqRAG, question: str, conversation_context: list[dict] | None, request: Request
) -> AsyncIterator[str]:
    async for event in rag.stream_response(question, conversation_context=conversation_context):
        if await request.is_disconnected():
            break
        yield _sse(event)


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    rag = get_rag()
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG system is still initializing")
    result = await rag.generate_response(req.question, conversation_context=req.conversation_context)
    return QueryResponse(
        answer=result["answer"],
        sources=[Source(**s) for s in result["sources"]],
        regulator=result["regulator"],
    )


@router.post("/query/stream")
async def query_stream(req: QueryRequest, request: Request) -> StreamingResponse:
    rag = get_rag()
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG system is still initializing")
    return StreamingResponse(
        _stream_events(rag, req.question, req.conversation_context, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
