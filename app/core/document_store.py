"""Disk-backed store for uploaded analysis documents.

Stateless API: each call is keyed by doc_id. Parsed text persists to a JSON
file under settings.analysis_docs_dir so a page refresh on the frontend
doesn't lose the uploaded document. Analysis results (compliance + brief)
are cached on the same record so post-scan language toggles are pure
lookups (no re-scan, no re-LLM).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_ID_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize(doc_id: str | None) -> str | None:
    if not isinstance(doc_id, str):
        return None
    cleaned = _ID_SAFE_RE.sub("", doc_id)
    return cleaned if cleaned else None


def _now() -> str:
    return datetime.now().isoformat()


class DocumentStore:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, doc_id: str) -> Path:
        return self.storage_dir / f"{doc_id}.json"

    def create(self, parsed: dict) -> str:
        """Persist a freshly parsed document. Returns the new doc_id."""
        doc_id = str(uuid.uuid4())[:8]
        record = {
            "id": doc_id,
            "uploaded_at": _now(),
            "filename": parsed["filename"],
            "page_count": parsed.get("page_count", 0),
            "char_count": parsed.get("char_count", 0),
            "summary": parsed.get("summary", {}),
            "text": parsed.get("text", ""),
            "compliance": None,
            "brief": None,
        }
        with open(self._path(doc_id), "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return doc_id

    def get(self, doc_id: str | None) -> dict | None:
        did = _sanitize(doc_id)
        if not did:
            return None
        fp = self._path(did)
        if not fp.exists():
            return None
        try:
            with open(fp, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read %s: %s", fp.name, e)
            return None

    def metadata(self, doc_id: str) -> dict | None:
        """Strip large/internal fields and surface boolean flags for the UI."""
        rec = self.get(doc_id)
        if rec is None:
            return None
        return {
            "id": rec.get("id", ""),
            "filename": rec.get("filename", ""),
            "uploaded_at": rec.get("uploaded_at", ""),
            "page_count": rec.get("page_count", 0),
            "char_count": rec.get("char_count", 0),
            "summary": rec.get("summary"),
            "has_compliance": rec.get("compliance") is not None,
            "has_brief": rec.get("brief") is not None,
        }

    def get_text(self, doc_id: str) -> str | None:
        rec = self.get(doc_id)
        return rec.get("text") if rec else None

    def set_compliance(self, doc_id: str, result: dict) -> bool:
        did = _sanitize(doc_id)
        if not did:
            return False
        rec = self.get(did)
        if rec is None:
            return False
        rec["compliance"] = result
        with open(self._path(did), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        return True

    def set_brief(self, doc_id: str, brief: dict) -> bool:
        did = _sanitize(doc_id)
        if not did:
            return False
        rec = self.get(did)
        if rec is None:
            return False
        rec["brief"] = brief
        with open(self._path(did), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        return True

    def delete(self, doc_id: str | None) -> bool:
        did = _sanitize(doc_id)
        if not did:
            return False
        fp = self._path(did)
        if fp.exists():
            fp.unlink()
            return True
        return False

    def list(self, limit: int = 20) -> list[dict]:
        out: list[dict] = []
        files = sorted(self.storage_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    rec = json.load(f)
            except Exception as e:
                logger.warning("Skipping unreadable %s: %s", fp.name, e)
                continue
            out.append({
                "id": rec.get("id", fp.stem),
                "filename": rec.get("filename", "Document"),
                "uploaded_at": rec.get("uploaded_at", ""),
                "page_count": rec.get("page_count", 0),
                "char_count": rec.get("char_count", 0),
                "has_compliance": rec.get("compliance") is not None,
                "has_brief": rec.get("brief") is not None,
            })
            if len(out) >= limit:
                break
        return out


_store: DocumentStore | None = None


def get_document_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = DocumentStore(settings.analysis_docs_dir)
    return _store
