import logging

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from app.core.analysis import ComplianceChecker, DocumentParseError, DocumentProcessor
from app.core.document_store import get_document_store
from app.core.rag import get_rag
from app.models.analysis import (
    BriefRequest,
    BriefResult,
    ComplianceRequest,
    ComplianceResult,
    DocumentListResponse,
    DocumentMetadata,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_processor = DocumentProcessor()
_checker = ComplianceChecker()


@router.post("/documents", response_model=DocumentMetadata, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> DocumentMetadata:
    filename = file.filename or "uploaded.pdf"
    data = await file.read()
    try:
        parsed = _processor.parse(data, filename)
    except DocumentParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    store = get_document_store()
    doc_id = store.create(parsed)
    meta = store.metadata(doc_id)
    return DocumentMetadata(**meta)


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(limit: int = 20) -> DocumentListResponse:
    return DocumentListResponse(documents=get_document_store().list(limit=limit))


@router.get("/documents/{doc_id}", response_model=DocumentMetadata)
def get_document(doc_id: str) -> DocumentMetadata:
    meta = get_document_store().metadata(doc_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return DocumentMetadata(**meta)


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str) -> Response:
    if not get_document_store().delete(doc_id):
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return Response(status_code=204)


@router.post("/documents/{doc_id}/compliance", response_model=ComplianceResult)
def run_compliance(doc_id: str, req: ComplianceRequest = ComplianceRequest()) -> ComplianceResult:
    store = get_document_store()
    rec = store.get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    text = rec.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Document text is empty")
    result = _checker.check(text, filename=rec.get("filename"), strictness=req.strictness)
    store.set_compliance(doc_id, result)
    return ComplianceResult(**result)


@router.get("/documents/{doc_id}/compliance", response_model=ComplianceResult)
def get_compliance(doc_id: str) -> ComplianceResult:
    rec = get_document_store().get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    cached = rec.get("compliance")
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="No compliance result cached. POST to this endpoint first to run a scan.",
        )
    return ComplianceResult(**cached)


@router.post("/documents/{doc_id}/brief", response_model=BriefResult)
async def run_brief(doc_id: str, req: BriefRequest = BriefRequest()) -> BriefResult:
    rag = get_rag()
    if not rag.ready:
        raise HTTPException(status_code=503, detail="RAG system is still initializing")
    store = get_document_store()
    rec = store.get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    text = rec.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Document text is empty")
    try:
        result = await rag.generate_brief(text, report_language=req.report_language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Brief generation failed for doc=%s", doc_id)
        raise HTTPException(status_code=500, detail=f"Brief generation failed: {e}") from e
    store.set_brief(doc_id, result)
    return BriefResult(**result)


@router.get("/documents/{doc_id}/brief", response_model=BriefResult)
def get_brief(doc_id: str) -> BriefResult:
    rec = get_document_store().get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    cached = rec.get("brief")
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="No brief cached. POST to this endpoint first to generate one.",
        )
    return BriefResult(**cached)
