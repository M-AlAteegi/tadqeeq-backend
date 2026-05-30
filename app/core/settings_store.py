"""Disk-backed user-settings store.

Single file under settings.settings_file. Pydantic-validated on read AND
write so a corrupt or partial JSON falls back to defaults rather than
crashing the server.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings as app_settings
from app.models.settings import UserSettings

logger = logging.getLogger(__name__)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> UserSettings:
        if not self.path.exists():
            return UserSettings()
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            return UserSettings(**raw)
        except Exception as e:
            logger.warning("Failed to load %s, falling back to defaults: %s", self.path, e)
            return UserSettings()

    def save(self, current: UserSettings) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(current.model_dump(), f, ensure_ascii=False, indent=2)

    def patch(self, updates: dict) -> UserSettings:
        """Apply a partial update and persist. Returns the merged settings."""
        current = self.load()
        merged = current.model_dump() | {k: v for k, v in updates.items() if v is not None}
        new = UserSettings(**merged)
        self.save(new)
        return new


_store: SettingsStore | None = None


def get_settings_store() -> SettingsStore:
    global _store
    if _store is None:
        _store = SettingsStore(app_settings.settings_file)
    return _store
