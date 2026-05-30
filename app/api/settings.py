from fastapi import APIRouter

from app.core.settings_store import get_settings_store
from app.models.settings import UserSettings, UserSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=UserSettings)
def get_settings() -> UserSettings:
    return get_settings_store().load()


@router.patch("", response_model=UserSettings)
def patch_settings(update: UserSettingsUpdate) -> UserSettings:
    return get_settings_store().patch(update.model_dump(exclude_unset=True))
