"""Metadata persisted for every benchmark session (one pair of documents)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.schemas.document import DocumentType, FileInfo


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionMeta(BaseModel):
    """`data/{session_id}/session.json`.

    The two readiness flags are the single source of truth for the UI gate on
    the "Рассчитать метрики" button.
    """

    session_id: str
    document_type: DocumentType
    created_at: str = Field(default_factory=_now)
    updated_at: str = _now

    reference: FileInfo | None = None
    recognized: FileInfo | None = None

    reference_json_ready: bool = False
    recognized_json_ready: bool = False
    metrics_ready: bool = False

    model: str | None = None
    warnings: list[str] = Field(default_factory=list)

    def touch(self) -> "SessionMeta":
        self.updated_at = _now()
        return self
