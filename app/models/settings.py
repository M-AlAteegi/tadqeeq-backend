from typing import Literal

from pydantic import BaseModel, Field


class UserSettings(BaseModel):
    """User-facing preferences. All optional with explicit defaults so a
    fresh client always sees a fully-populated object."""

    rigor_level: Literal["standard", "deep"] = Field(default="standard")
    strictness: Literal["standard", "critical_only"] = Field(default="standard")
    report_language: Literal["auto", "en", "ar", "bilingual"] = Field(default="auto")
    date_format: Literal["dual", "gregorian", "hijri"] = Field(default="dual")
    brief_language: Literal["auto", "en", "ar", "bilingual"] = Field(default="auto")
    brief_date_format: Literal["dual", "gregorian", "hijri"] = Field(default="dual")


class UserSettingsUpdate(BaseModel):
    """PATCH shape — every field optional, server applies only the keys present."""

    rigor_level: Literal["standard", "deep"] | None = None
    strictness: Literal["standard", "critical_only"] | None = None
    report_language: Literal["auto", "en", "ar", "bilingual"] | None = None
    date_format: Literal["dual", "gregorian", "hijri"] | None = None
    brief_language: Literal["auto", "en", "ar", "bilingual"] | None = None
    brief_date_format: Literal["dual", "gregorian", "hijri"] | None = None
