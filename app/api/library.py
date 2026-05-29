import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.history import get_library_store
from app.core.library import get_library
from app.core.rag import TadqeeqRAG, get_rag
from app.models.chat import Source
from app.models.library import ClauseDetail, LibraryIndex, LibraryQueryRequest, LibraryQueryResponse

router = APIRouter(prefix="/api/library", tags=["library"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _resolve_chat_id(req: LibraryQueryRequest) -> str | None:
    if req.chat_id:
        return req.chat_id
    if req.create_chat:
        return get_library_store().create(category_id=req.category_id)
    return None


@router.get("/index", response_model=LibraryIndex)
def index() -> LibraryIndex:
    return LibraryIndex(**get_library().get_index())


@router.get("/clause/{clause_id}", response_model=ClauseDetail)
def clause(clause_id: str) -> ClauseDetail:
    record = get_library().get_clause(clause_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Clause not found: {clause_id}")
    return ClauseDetail(**record)


@router.post("/query", response_model=LibraryQueryResponse)
async def library_query(req: LibraryQueryRequest) -> LibraryQueryResponse:
    rag = get_rag()
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG system is still initializing")
    chat_id = _resolve_chat_id(req)
    store = get_library_store()
    if chat_id:
        store.add_message(chat_id, "user", req.question)
    result = await rag.generate_response(req.question, force_no_followup=True)
    if chat_id:
        store.add_message(
            chat_id, "assistant", result["answer"],
            sources=result["sources"], regulator=result["regulator"],
        )
    return LibraryQueryResponse(
        answer=result["answer"],
        sources=[Source(**s) for s in result["sources"]],
        regulator=result["regulator"],
        chat_id=chat_id,
    )


async def _stream_events(
    rag: TadqeeqRAG, req: LibraryQueryRequest, request: Request
) -> AsyncIterator[str]:
    chat_id = _resolve_chat_id(req)
    store = get_library_store()
    if chat_id:
        yield _sse({"type": "chat", "chat_id": chat_id})
        store.add_message(chat_id, "user", req.question)
    accumulated: list[str] = []
    last_sources: list[dict] = []
    last_regulator: str = "BOTH"
    aborted = False
    try:
        async for event in rag.stream_response(req.question, force_no_followup=True):
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
        if chat_id and accumulated:
            text = "".join(accumulated).strip()
            if aborted:
                text += "\n\n_[stopped]_"
            store.add_message(
                chat_id, "assistant", text, sources=last_sources, regulator=last_regulator
            )


@router.post("/query/stream")
async def library_query_stream(req: LibraryQueryRequest, request: Request) -> StreamingResponse:
    rag = get_rag()
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG system is still initializing")
    return StreamingResponse(
        _stream_events(rag, req, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
