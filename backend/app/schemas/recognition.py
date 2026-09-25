"""Metadata recorded while a document is pushed through GLM 4.6."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Token accounting as reported by the API `usage` object."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )


class PageRecognitionMeta(BaseModel):
    page_number: int
    model: str
    request_seconds: float
    usage: TokenUsage = Field(default_factory=TokenUsage)
    text_blocks: int = 0
    table_blocks: int = 0
    image_blocks: int = 0
    raw_response_chars: int = 0
    attempts: int = 1
    error: str | None = None


class RecognitionMeta(BaseModel):
    """Everything about the GLM run, stored next to `recognized.json`."""

    session_id: str
    model: str
    requested_models: list[str] = Field(default_factory=list)
    fallback_models: list[str] = Field(default_factory=list)
    request_seconds: float = 0.0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    pages: list[PageRecognitionMeta] = Field(default_factory=list)
    render_dpi: int = 0
    prompt_version: str = "v1"
    started_at: str = ""
    finished_at: str = ""
    warnings: list[str] = Field(default_factory=list)
