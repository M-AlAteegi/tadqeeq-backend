from pydantic import BaseModel, Field

from app.models.chat import Source


class Message(BaseModel):
    role: str
    content: str
    timestamp: str = ""
    sources: list[Source] = []
    regulator: str | None = None


class ChatSummary(BaseModel):
    id: str
    preview: str
    updated: str = ""
    message_count: int = 0
    regulator: str | None = None


class ChatDetail(BaseModel):
    id: str
    created: str = ""
    updated: str = ""
    preview: str = ""
    messages: list[Message] = []


class LibraryChatSummary(ChatSummary):
    category_id: str | None = None


class LibraryChatDetail(ChatDetail):
    category_id: str | None = None


class NewChatRequest(BaseModel):
    pass


class NewChatResponse(BaseModel):
    id: str


class NewLibraryChatRequest(BaseModel):
    category_id: str | None = Field(default=None)


class ChatListResponse(BaseModel):
    chats: list[ChatSummary]


class LibraryChatListResponse(BaseModel):
    chats: list[LibraryChatSummary]
