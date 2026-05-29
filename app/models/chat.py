from pydantic import BaseModel, Field, field_validator


class Source(BaseModel):
    article: str
    document: str
    title: str = ""


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    chat_id: str | None = Field(
        default=None,
        description="If provided, append user + assistant messages to this chat. "
        "If omitted, the query is one-shot and not persisted.",
    )
    conversation_context: list[dict] | None = Field(
        default=None,
        description="Optional prior turns for follow-up clarification. If omitted "
        "and chat_id is provided, the server uses the last 6 messages of that chat.",
    )

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question cannot be empty")
        return v


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    regulator: str
