from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = Field(default="claude", description="claude | ollama")

    claude_api_key: str = Field(default="")
    claude_model: str = Field(default="claude-haiku-4-5-20251001")

    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="aya:8b")

    tadqeeq_data_dir: Path = Field(default=Path("../TadqeeqAI"))
    chat_history_dir: Path = Field(default=Path("./data/chat_history"))
    library_chat_history_dir: Path = Field(default=Path("./data/library_chat_history"))
    settings_file: Path = Field(default=Path("./data/settings.json"))

    embedding_model: str = Field(default="intfloat/multilingual-e5-base")
    chroma_collection: str = Field(default="tadqeeq_v2")
    chat_num_predict: int = Field(default=800)

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.lstrip()
            if stripped.startswith("["):
                import json
                return json.loads(v)
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def chroma_path(self) -> Path:
        return self.tadqeeq_data_dir / "chroma_db_v2"

    @property
    def bm25_path(self) -> Path:
        return self.tadqeeq_data_dir / "bm25_index.pkl"

    @property
    def documents_path(self) -> Path:
        return self.tadqeeq_data_dir / "documents.json"

    @property
    def clauses_path(self) -> Path:
        return self.tadqeeq_data_dir / "clauses.json"


settings = Settings()
