"""Pydantic models describing the API contract."""

from app.schemas.api import (
    DocumentTypeInfo,
    ErrorResponse,
    MetricsRequest,
    MetricsResponse,
    RecognizeRequest,
    RecognizeResponse,
    ResultsResponse,
    SessionSummary,
    UploadResponse,
)
from app.schemas.document import (
    BlockType,
    DocumentBlock,
    DocumentJSON,
    DocumentPage,
    DocumentSource,
    DocumentType,
    EntitySet,
    FileInfo,
    ImageBlock,
    TableBlock,
    TextBlock,
)

__all__ = [
    "BlockType",
    "DocumentBlock",
    "DocumentJSON",
    "DocumentPage",
    "DocumentSource",
    "DocumentType",
    "DocumentTypeInfo",
    "EntitySet",
    "ErrorResponse",
    "FileInfo",
    "ImageBlock",
    "MetricsRequest",
    "MetricsResponse",
    "RecognizeRequest",
    "RecognizeResponse",
    "ResultsResponse",
    "SessionSummary",
    "TableBlock",
    "TextBlock",
    "UploadResponse",
]
