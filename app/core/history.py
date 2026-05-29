"""File-based chat history persistence.

Stateless — every operation is scoped to a chat_id supplied by the caller.
Unlike the v3.x PyWebView design (which kept a `current_chat_id` instance
attribute), a REST backend serves many concurrent clients and cannot hold
per-client mutable state. The frontend owns "which chat is open"; the
backend is just a key-value store keyed by chat_id.

Two stores parallel the v3.x design:
    - RegularChatStore: chat-mode conversations
    - LibraryChatStore: library-mode conversations (carries category_id)
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_ID_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _now() -> str:
    return datetime.now().isoformat()


def _sanitize_id(chat_id: str | None) -> str | None:
    """Strip anything that isn't alphanumeric, dash, or underscore.

    Prevents path traversal via crafted ids like '../../etc/passwd'.
    """
    if not isinstance(chat_id, str):
        return None
    cleaned = _ID_SAFE_RE.sub("", chat_id)
    return cleaned if cleaned else None


class _BaseStore:
    DEFAULT_PREVIEW = "Chat"

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, chat_id: str) -> Path:
        return self.storage_dir / f"{chat_id}.json"

    def _load_raw(self, chat_id: str) -> dict | None:
        fp = self._path(chat_id)
        if not fp.exists():
            return None
        try:
            with open(fp, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read %s: %s", fp.name, e)
            return None

    def _save_raw(self, chat_id: str, data: dict) -> None:
        with open(self._path(chat_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _compute_preview(self, messages: list[dict]) -> str:
        for m in messages:
            if m.get("role") == "user":
                text = m.get("content", "")
                return text[:50] + "..." if len(text) > 50 else text
        return self.DEFAULT_PREVIEW

    def _new_record(self) -> dict:
        return {"created": _now(), "updated": _now(), "messages": [], "preview": self.DEFAULT_PREVIEW}

    def get(self, chat_id: str | None) -> dict | None:
        cid = _sanitize_id(chat_id)
        if not cid:
            return None
        return self._load_raw(cid)

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        regulator: str | None = None,
    ) -> bool:
        cid = _sanitize_id(chat_id)
        if not cid:
            return False
        data = self._load_raw(cid)
        if data is None:
            data = self._new_record() | {"id": cid}
        msg: dict = {"role": role, "content": content, "timestamp": _now()}
        if sources:
            msg["sources"] = sources
        if regulator:
            msg["regulator"] = regulator
        data["messages"].append(msg)
        data["updated"] = msg["timestamp"]
        data["preview"] = self._compute_preview(data["messages"])
        self._save_raw(cid, data)
        return True

    def delete(self, chat_id: str | None) -> bool:
        cid = _sanitize_id(chat_id)
        if not cid:
            return False
        fp = self._path(cid)
        if fp.exists():
            fp.unlink()
            return True
        return False

    def conversation_context(self, chat_id: str, limit: int = 6) -> list[dict]:
        data = self.get(chat_id)
        if not data:
            return []
        msgs = data.get("messages", [])
        return [{"role": m["role"], "content": m["content"]} for m in msgs[-limit:]]

    def _summarize_for_list(self, data: dict) -> dict:
        return {
            "id": data["id"],
            "preview": data.get("preview", self.DEFAULT_PREVIEW),
            "updated": data.get("updated", ""),
            "message_count": len(data.get("messages", [])),
        }

    def list(self, limit: int = 20) -> list[dict]:
        out: list[dict] = []
        files = sorted(self.storage_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                if "id" not in data:
                    data["id"] = fp.stem
                out.append(self._summarize_for_list(data))
            except Exception as e:
                logger.warning("Skipping unreadable %s: %s", fp.name, e)
            if len(out) >= limit:
                break
        return out


class RegularChatStore(_BaseStore):
    """Regular-chat history. Summary carries the first non-NONE/BOTH regulator
    so the sidebar can color-badge the chat by topic."""

    def create(self) -> str:
        cid = str(uuid.uuid4())[:8]
        data = self._new_record() | {"id": cid}
        self._save_raw(cid, data)
        return cid

    def _summarize_for_list(self, data: dict) -> dict:
        regulator = None
        for m in data.get("messages", []):
            r = m.get("regulator")
            if r and r not in ("NONE", "BOTH"):
                regulator = r
                break
        return super()._summarize_for_list(data) | {"regulator": regulator}


class LibraryChatStore(_BaseStore):
    """Library-chat history. Each chat carries a `category_id` so the sidebar
    can paint a category-color badge without re-reading the chat body."""

    DEFAULT_PREVIEW = "Library Chat"
    _PRIMER_RE = re.compile(
        r"^I'm reviewing the following .+?\. Please help me adapt or assess it:\s*",
        re.DOTALL,
    )

    def create(self, category_id: str | None = None) -> str:
        cid = str(uuid.uuid4())[:8]
        data = self._new_record() | {"id": cid, "category_id": category_id}
        self._save_raw(cid, data)
        return cid

    def _compute_preview(self, messages: list[dict]) -> str:
        for m in messages:
            if m.get("role") == "user":
                text = m.get("content", "")
                primer = self._PRIMER_RE.match(text)
                if primer:
                    rest = text[primer.end():].strip()
                    lines = [ln.strip() for ln in rest.split("\n") if ln.strip()]
                    if lines:
                        text = lines[-1]
                return text[:50] + "..." if len(text) > 50 else text
        return self.DEFAULT_PREVIEW

    def _summarize_for_list(self, data: dict) -> dict:
        return super()._summarize_for_list(data) | {"category_id": data.get("category_id")}


_regular_store: RegularChatStore | None = None
_library_store: LibraryChatStore | None = None


def get_regular_store() -> RegularChatStore:
    global _regular_store
    if _regular_store is None:
        from app.config import settings
        _regular_store = RegularChatStore(settings.chat_history_dir)
    return _regular_store


def get_library_store() -> LibraryChatStore:
    global _library_store
    if _library_store is None:
        from app.config import settings
        _library_store = LibraryChatStore(settings.library_chat_history_dir)
    return _library_store
