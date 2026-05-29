import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.library import get_library
from app.core.rag import TadqeeqRAG, get_rag
from app.models.chat import Source
from app.models.library import ClauseDetail, LibraryIndex, LibraryQueryRequest, LibraryQueryResponse

router = APIRouter(prefix="/api/library", tags=["library"])


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
    result = await rag.generate_response(req.question, force_no_followup=True)
    return LibraryQueryResponse(
        answer=result["answer"],
        sources=[Source(**s) for s in result["sources"]],
        regulator=result["regulator"],
    )


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _stream_events(rag: TadqeeqRAG, question: str, request: Request) -> AsyncIterator[str]:
    async for event in rag.stream_response(question, force_no_followup=True):
        if await request.is_disconnected():
            break
        yield _sse(event)


@router.post("/query/stream")
async def library_query_stream(req: LibraryQueryRequest, request: Request) -> StreamingResponse:
    rag = get_rag()
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG system is still initializing")
    return StreamingResponse(
        _stream_events(rag, req.question, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
