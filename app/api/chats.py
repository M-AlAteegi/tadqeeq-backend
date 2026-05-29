from fastapi import APIRouter, HTTPException, Response

from app.core.history import get_regular_store
from app.models.history import (
    ChatDetail,
    ChatListResponse,
    NewChatRequest,
    NewChatResponse,
)

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.post("", response_model=NewChatResponse, status_code=201)
def create_chat(_: NewChatRequest = NewChatRequest()) -> NewChatResponse:
    return NewChatResponse(id=get_regular_store().create())


@router.get("", response_model=ChatListResponse)
def list_chats(limit: int = 20) -> ChatListResponse:
    return ChatListResponse(chats=get_regular_store().list(limit=limit))


@router.get("/{chat_id}", response_model=ChatDetail)
def get_chat(chat_id: str) -> ChatDetail:
    data = get_regular_store().get(chat_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")
    return ChatDetail(**data)


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: str) -> Response:
    if not get_regular_store().delete(chat_id):
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")
    return Response(status_code=204)
