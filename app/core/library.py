"""Curated Islamic-finance clause library.

Read-only: ships as part of the app and is not mutated at runtime.
Loaded once at startup via the module-level singleton get_library().
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class ClauseLibrary:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {"version": "0", "categories": [], "clauses": []}
        path = settings.clauses_path
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(
                    "Clause library loaded: %d categories, %d clauses",
                    len(self._data.get("categories", [])),
                    len(self._data.get("clauses", [])),
                )
            except Exception as e:
                logger.warning("Failed to load %s (%s) — library will be empty.", path, e)
        else:
            logger.warning("clauses.json not found at %s — library will be empty.", path)

    def get_index(self) -> dict:
        """Categories + slim clause summaries (no bodies)."""
        return {
            "categories": [dict(c) for c in self._data.get("categories", [])],
            "clauses": [
                {
                    "id": c.get("id", ""),
                    "category": c.get("category", ""),
                    "type": c.get("type", "clause"),
                    "title_en": c.get("title_en", ""),
                    "title_ar": c.get("title_ar", ""),
                    "tags": list(c.get("tags", [])),
                }
                for c in self._data.get("clauses", [])
            ],
        }

    def get_clause(self, clause_id: str) -> dict | None:
        if not isinstance(clause_id, str) or not clause_id:
            return None
        for c in self._data.get("clauses", []):
            if c.get("id") == clause_id:
                return dict(c)
        return None


_library_instance: ClauseLibrary | None = None


def get_library() -> ClauseLibrary:
    global _library_instance
    if _library_instance is None:
        _library_instance = ClauseLibrary()
    return _library_instance
