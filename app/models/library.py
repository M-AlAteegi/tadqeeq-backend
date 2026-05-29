from pydantic import BaseModel, Field, field_validator

from app.models.chat import Source


class Category(BaseModel):
    id: str
    label_en: str
    label_ar: str = ""


class ClauseSummary(BaseModel):
    id: str
    category: str
    type: str = "clause"
    title_en: str = ""
    title_ar: str = ""
    tags: list[str] = []


class ClauseDetail(ClauseSummary):
    body_en: str = ""
    body_ar: str = ""
    source_note: str = ""


class LibraryIndex(BaseModel):
    categories: list[Category]
    clauses: list[ClauseSummary]


class LibraryQueryRequest(BaseModel):
    """Library queries inline a full clause/contract template as context, so
    the question cap is raised from the chat-mode 2000 to 20000."""

    question: str = Field(..., min_length=1, max_length=20_000)
    chat_id: str | None = Field(
        default=None,
        description="If provided, append user + assistant messages to this library chat.",
    )
    category_id: str | None = Field(
        default=None,
        description="If chat_id is omitted and create_chat is True, the server "
        "creates a new library chat bound to this category (sidebar badge color).",
    )
    create_chat: bool = Field(
        default=False,
        description="If True and chat_id is omitted, server creates a new chat and "
        "returns the id in the first SSE event (stream) or response body (one-shot).",
    )

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question cannot be empty")
        return v


class LibraryQueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    regulator: str
    chat_id: str | None = None
