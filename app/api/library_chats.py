from fastapi import APIRouter, HTTPException, Response

from app.core.history import get_library_store
from app.models.history import (
    LibraryChatDetail,
    LibraryChatListResponse,
    NewChatResponse,
    NewLibraryChatRequest,
)

router = APIRouter(prefix="/api/library/chats", tags=["library-chats"])


@router.post("", response_model=NewChatResponse, status_code=201)
def create_library_chat(req: NewLibraryChatRequest = NewLibraryChatRequest()) -> NewChatResponse:
    return NewChatResponse(id=get_library_store().create(category_id=req.category_id))


@router.get("", response_model=LibraryChatListResponse)
def list_library_chats(limit: int = 20) -> LibraryChatListResponse:
    return LibraryChatListResponse(chats=get_library_store().list(limit=limit))


@router.get("/{chat_id}", response_model=LibraryChatDetail)
def get_library_chat(chat_id: str) -> LibraryChatDetail:
    data = get_library_store().get(chat_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Library chat not found: {chat_id}")
    return LibraryChatDetail(**data)


@router.delete("/{chat_id}", status_code=204)
def delete_library_chat(chat_id: str) -> Response:
    if not get_library_store().delete(chat_id):
        raise HTTPException(status_code=404, detail=f"Library chat not found: {chat_id}")
    return Response(status_code=204)
