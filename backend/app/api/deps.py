"""FastAPI dependencies (single process-wide store instances)."""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.services.images import ImageStore
from app.services.storage import SessionStore


@lru_cache
def get_session_store() -> SessionStore:
    return SessionStore(get_settings().data_path)


@lru_cache
def get_image_store() -> ImageStore:
    return ImageStore(get_settings().data_path)


def get_settings_dep() -> Settings:
    return get_settings()
