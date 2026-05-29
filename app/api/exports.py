"""Export endpoints for chat, library, and brief artifacts.

Each export type ships in three formats: Markdown (always available), DOCX
(via app/core/exports_docx.py), and PDF (via app/core/exports_pdf.py).
DOCX + PDF are wired in their respective sub-routers — this module covers
Markdown only.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.document_store import get_document_store
from app.core.exports import (
    export_brief_markdown,
    export_chat_markdown,
    export_library_markdown,
)
from app.core.exports_docx import (
    export_brief_docx,
    export_chat_docx,
    export_library_docx,
)
from app.core.exports_pdf import (
    export_brief_pdf,
    export_chat_pdf,
    export_library_pdf,
)
from app.core.history import get_library_store, get_regular_store
from app.core.library import get_library

router = APIRouter(tags=["exports"])

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(stem: str, ext: str) -> str:
    cleaned = _FILENAME_SAFE.sub("_", stem).strip("_")
    return f"{cleaned or 'export'}.{ext}"


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _md_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _docx_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _category_label(category_id: str | None) -> str:
    if not category_id:
        return ""
    for cat in get_library().get_index()["categories"]:
        if cat["id"] == category_id:
            return cat.get("label_en", "")
    return ""


@router.get("/api/chats/{chat_id}/export/markdown")
def export_chat_md(chat_id: str, date_format: str = "dual") -> Response:
    chat = get_regular_store().get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")
    md = export_chat_markdown(chat.get("messages", []), date_format=date_format)
    return _md_response(md, _safe_filename(f"tadqeeq-chat-{chat_id}", "md"))


@router.get("/api/library/chats/{chat_id}/export/markdown")
def export_library_chat_md(chat_id: str, date_format: str = "dual") -> Response:
    chat = get_library_store().get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Library chat not found: {chat_id}")
    md = export_library_markdown(
        chat.get("messages", []),
        category_label=_category_label(chat.get("category_id")),
        clause_title="",
        date_format=date_format,
    )
    return _md_response(md, _safe_filename(f"tadqeeq-library-{chat_id}", "md"))


@router.get("/api/analysis/documents/{doc_id}/brief/export/markdown")
def export_brief_md(doc_id: str, date_format: str = "dual") -> Response:
    rec = get_document_store().get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    brief = rec.get("brief")
    if not brief or not brief.get("report"):
        raise HTTPException(
            status_code=404,
            detail="No brief cached for this document. Generate one first via "
            "POST /api/analysis/documents/{id}/brief.",
        )
    md = export_brief_markdown(brief["report"], date_format=date_format)
    fname = _safe_filename(f"tadqeeq-brief-{rec.get('filename', doc_id)}", "md")
    return _md_response(md, fname)


@router.get("/api/chats/{chat_id}/export/docx")
def export_chat_docx_endpoint(chat_id: str, date_format: str = "dual") -> Response:
    chat = get_regular_store().get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")
    data = export_chat_docx(chat.get("messages", []), date_format=date_format)
    return _docx_response(data, _safe_filename(f"tadqeeq-chat-{chat_id}", "docx"))


@router.get("/api/library/chats/{chat_id}/export/docx")
def export_library_chat_docx_endpoint(chat_id: str, date_format: str = "dual") -> Response:
    chat = get_library_store().get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Library chat not found: {chat_id}")
    data = export_library_docx(
        chat.get("messages", []),
        category_label=_category_label(chat.get("category_id")),
        clause_title="",
        date_format=date_format,
    )
    return _docx_response(data, _safe_filename(f"tadqeeq-library-{chat_id}", "docx"))


@router.get("/api/analysis/documents/{doc_id}/brief/export/docx")
def export_brief_docx_endpoint(doc_id: str, date_format: str = "dual") -> Response:
    rec = get_document_store().get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    brief = rec.get("brief")
    if not brief or not brief.get("report"):
        raise HTTPException(
            status_code=404,
            detail="No brief cached. Generate one first via "
            "POST /api/analysis/documents/{id}/brief.",
        )
    data = export_brief_docx(brief["report"], date_format=date_format)
    fname = _safe_filename(f"tadqeeq-brief-{rec.get('filename', doc_id)}", "docx")
    return _docx_response(data, fname)


@router.get("/api/chats/{chat_id}/export/pdf")
def export_chat_pdf_endpoint(chat_id: str, date_format: str = "dual") -> Response:
    chat = get_regular_store().get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")
    data = export_chat_pdf(chat.get("messages", []), date_format=date_format)
    return _pdf_response(data, _safe_filename(f"tadqeeq-chat-{chat_id}", "pdf"))


@router.get("/api/library/chats/{chat_id}/export/pdf")
def export_library_chat_pdf_endpoint(chat_id: str, date_format: str = "dual") -> Response:
    chat = get_library_store().get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Library chat not found: {chat_id}")
    data = export_library_pdf(
        chat.get("messages", []),
        category_label=_category_label(chat.get("category_id")),
        clause_title="",
        date_format=date_format,
    )
    return _pdf_response(data, _safe_filename(f"tadqeeq-library-{chat_id}", "pdf"))


@router.get("/api/analysis/documents/{doc_id}/brief/export/pdf")
def export_brief_pdf_endpoint(doc_id: str, date_format: str = "dual") -> Response:
    rec = get_document_store().get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    brief = rec.get("brief")
    if not brief or not brief.get("report"):
        raise HTTPException(
            status_code=404,
            detail="No brief cached. Generate one first via "
            "POST /api/analysis/documents/{id}/brief.",
        )
    data = export_brief_pdf(brief["report"], date_format=date_format)
    fname = _safe_filename(f"tadqeeq-brief-{rec.get('filename', doc_id)}", "pdf")
    return _pdf_response(data, fname)
